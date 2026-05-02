import os
from datetime import datetime, timedelta, timezone
from flask import Flask, flash, jsonify, redirect, request, session, url_for  # ✅ FIXED: Added jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv  # ✅ FIXED: Now works after pip install
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables FIRST
load_dotenv()

# Initialize extensions (module-level)
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
jwt = JWTManager()

def create_app(config_name='default'):
    """
    Factory function to create Flask application
    """
    # Resolve paths from the current package instead of a hardcoded machine-specific folder.
    app_dir = os.path.abspath(os.path.dirname(__file__))
    backend_dir = os.path.dirname(app_dir)
    
    # Create app instance
    app = Flask(__name__, 
                template_folder=os.path.join(app_dir, 'templates'),
                static_folder=os.path.join(app_dir, 'static'),
                instance_relative_config=True)
    
    # Load config from config.py
    from .config import config
    app.config.from_object(config[config_name])
    
    # Override with environment variables
    app.config.from_prefixed_env()

    proxy_fix_options = {
        'x_for': int(app.config.get('PROXY_FIX_X_FOR', 0) or 0),
        'x_proto': int(app.config.get('PROXY_FIX_X_PROTO', 0) or 0),
        'x_host': int(app.config.get('PROXY_FIX_X_HOST', 0) or 0),
        'x_port': int(app.config.get('PROXY_FIX_X_PORT', 0) or 0),
        'x_prefix': int(app.config.get('PROXY_FIX_X_PREFIX', 0) or 0),
    }
    if any(proxy_fix_options.values()):
        app.wsgi_app = ProxyFix(app.wsgi_app, **proxy_fix_options)
    
    # ========================================
    # JWT Configuration (Secure)
    # ========================================
    app.config.setdefault('SESSION_TIMEOUT_MINUTES', 60)
    app.config.setdefault(
        'SESSION_TIMEOUT_SECONDS',
        app.config['SESSION_TIMEOUT_MINUTES'] * 60,
    )
    app.config.setdefault(
        'PERMANENT_SESSION_LIFETIME',
        timedelta(seconds=app.config['SESSION_TIMEOUT_SECONDS']),
    )
    app.config.setdefault('SESSION_REFRESH_EACH_REQUEST', False)
    app.config.setdefault('JWT_SECRET_KEY', os.environ.get('JWT_SECRET_KEY', app.config['SECRET_KEY']))
    app.config.setdefault('JWT_ACCESS_TOKEN_EXPIRES', False)
    app.config.setdefault('JWT_TOKEN_LOCATION', ['cookies', 'headers', 'json'])
    app.config.setdefault('JWT_COOKIE_CSRF_PROTECT', True)
    app.config.setdefault('JWT_COOKIE_SECURE', app.config.get('SESSION_COOKIE_SECURE', False))
    
    # ========================================
    # Initialize Extensions
    # ========================================
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    CORS(app, supports_credentials=True)
    
    # Login Manager Configuration
    login_manager.login_view = 'auth_bp.login'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    def get_expired_session_redirect():
        if session.get('role') == 'super_admin':
            return url_for('owner_bp.login')
        if session.get('admin_id'):
            return url_for('admin_bp.admin_login')
        if session.get('is_super_admin'):
            return url_for('admin_bp.super_admin_login')
        return url_for('auth_bp.login')

    @app.before_request
    def enforce_session_timeout():
        endpoint = request.endpoint or ''
        exempt_endpoints = {
            'static',
            'health_check',
            'auth_bp.login',
            'auth_bp.logout',
            'auth_bp.register',
            'owner_bp.login',
            'admin_bp.admin_login',
            'admin_bp.super_admin_login',
        }

        if endpoint in exempt_endpoints or endpoint.endswith('.static'):
            return None

        has_tracked_session = any((
            session.get('user_id') is not None,
            session.get('admin_id') is not None,
            session.get('is_super_admin') is True,
        ))

        if not has_tracked_session:
            return None

        session.permanent = True
        now_ts = int(datetime.now(timezone.utc).timestamp())
        expires_at = session.get('session_expires_at')

        if expires_at is None:
            session['session_started_at'] = now_ts
            session['session_expires_at'] = now_ts + app.config['SESSION_TIMEOUT_SECONDS']
            return None

        try:
            expires_at = int(expires_at)
        except (TypeError, ValueError):
            redirect_target = get_expired_session_redirect()
            session.clear()
            flash('Your session data was invalid. Please log in again.', 'warning')
            return redirect(redirect_target)

        if now_ts >= expires_at:
            redirect_target = get_expired_session_redirect()
            session.clear()
            flash('Your session expired after 60 minutes. Please log in again.', 'warning')
            return redirect(redirect_target)
    
    # ========================================
    # Register Blueprints (Safe imports)
    # ========================================
    try:
        from .routes.main_routes import main_bp
        from .routes.auth_routes import auth_bp
        from .routes.admin_routes import admin_bp
        from .routes.user_routes import user_bp
        from .routes.api_routes import api_bp
        from .routes.complaint_routes import complaint_bp
        
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(user_bp, url_prefix='/user')
        app.register_blueprint(api_bp)
        app.register_blueprint(complaint_bp)
        
    except ImportError as e:
        app.logger.warning(f"Blueprint import failed (normal during dev): {e}")
    
    # ========================================
    # Database Setup
    # ========================================
    with app.app_context():
        db.create_all()
        
        @app.route('/health')
        def health_check():
            return jsonify({
                'status': 'healthy',
                'database': db.engine.has_table('users') if hasattr(db, 'engine') else False,
                'timestamp': os.popen('date').read().strip()
            })
    
    # ========================================
    # JWT Error Handlers ✅ FIXED jsonify
    # ========================================
    @app.errorhandler(401)
    def jwt_unauthorized(e):
        return jsonify({'message': 'Missing or invalid token', 'error': 'unauthorized'}), 401
    
    @app.errorhandler(403)
    def jwt_forbidden(e):
        return jsonify({'message': 'Access forbidden', 'error': 'forbidden'}), 403
    
    # Flask-Login unauthorized handler
    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({'message': 'Login required', 'error': 'unauthorized'}), 401

    @app.context_processor
    def inject_session_timeout():
        expires_at = session.get('session_expires_at')
        try:
            expires_at = int(expires_at) if expires_at is not None else None
        except (TypeError, ValueError):
            expires_at = None

        announcement_items = []
        announcement_count = 0
        announcement_unread_ids = []
        role = session.get('role')
        state_id = session.get('scope_state_id')
        district_id = session.get('scope_district_id')

        if role in ('worker', 'admin', 'district_admin', 'state_admin') and state_id:
            conn = None
            try:
                from app.utils.db import get_db
                from app.utils.staff_portal import fetch_unread_announcements, fetch_visible_announcements

                conn = get_db()
                cursor = conn.cursor(dictionary=True)
                announcement_items = fetch_visible_announcements(
                    cursor,
                    role,
                    state_id=state_id,
                    district_id=district_id,
                    limit=8,
                )
                if role in ('worker', 'admin', 'district_admin'):
                    unread_items = fetch_unread_announcements(
                        cursor,
                        role,
                        session.get('user_id'),
                        state_id=state_id,
                        district_id=district_id,
                        limit=8,
                    )
                    announcement_unread_ids = [item.get('id') for item in unread_items if item.get('id')]
                    announcement_count = len(announcement_unread_ids)
                else:
                    announcement_count = len(announcement_items)
            except Exception as err:
                print(f"Announcement context error: {err}")
            finally:
                if conn:
                    conn.close()

        return {
            'session_timeout_minutes': app.config.get('SESSION_TIMEOUT_MINUTES', 60),
            'session_expires_at_ts': expires_at,
            'announcement_items': announcement_items,
            'announcement_count': announcement_count,
            'announcement_unread_ids': announcement_unread_ids,
        }
    
    # ========================================
    # Shell Context Processor
    # ========================================
    @app.shell_context_processor
    def make_shell_context():
        return dict(app=app, db=db, bcrypt=bcrypt)
    
    return app

@login_manager.user_loader
def load_user(user_id):
    """Load user from database for Flask-Login"""
    try:
        from app.models.user_model import DistrictAdmin, TalukaAdmin, VillageWorker, CitizenUser
        
        # Try different user types
        users = [DistrictAdmin, TalukaAdmin, VillageWorker, CitizenUser]
        for UserClass in users:
            if hasattr(UserClass, 'query'):
                user = UserClass.query.get(int(user_id))
                if user:
                    return user
    except ImportError:
        pass
    return None
