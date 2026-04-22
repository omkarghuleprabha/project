import os
from flask import Flask, jsonify, request, redirect, session, url_for  # ✅ FIXED: Added jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv  # ✅ FIXED: Now works after pip install
from app.utils.auth import is_protected_path, role_dashboard_endpoint, should_disable_cache, sync_session_from_jwt

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
    # Set base directory
    BASE_DIR = r"D:\INTERSHIP\Garbage Management System\Garbage Management System\smart-garbage-management"
    
    # Create app instance
    app = Flask(__name__, 
                template_folder=os.path.join(BASE_DIR, 'backend', 'app', 'templates'),
                static_folder=os.path.join(BASE_DIR, 'backend', 'app', 'static'),
                instance_relative_config=True)
    
    # Load config from config.py
    from .config import config
    app.config.from_object(config[config_name])
    
    # Override with environment variables
    app.config.from_prefixed_env()
    
    # ========================================
    # JWT Configuration (Secure)
    # ========================================
    app.config.setdefault('JWT_SECRET_KEY', os.environ.get('JWT_SECRET_KEY', app.config['SECRET_KEY']))
    app.config.setdefault('JWT_TOKEN_LOCATION', ['cookies'])
    app.config.setdefault('JWT_COOKIE_CSRF_PROTECT', True)
    app.config.setdefault('JWT_COOKIE_SECURE', app.config.get('SESSION_COOKIE_SECURE', False))
    app.config.setdefault('JWT_ACCESS_COOKIE_NAME', 'sgms_access_token')
    app.config.setdefault('JWT_REFRESH_COOKIE_NAME', 'sgms_refresh_token')
    app.config.setdefault('JWT_COOKIE_SAMESITE', app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'))
    
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
    
    # ========================================
    # Register Blueprints (Safe imports)
    # ========================================
    try:
        from .routes.main_routes import main_bp
        from .routes.auth_routes import auth_bp
        from .routes.admin_routes import admin_bp
        from .routes.user_routes import user_bp
        from .routes.complaint_routes import complaint_bp
        from .routes.legacy_routes import legacy_bp
        from .routes.api_routes import api_bp
        
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(user_bp, url_prefix='/user')
        app.register_blueprint(complaint_bp)
        app.register_blueprint(legacy_bp)
        app.register_blueprint(api_bp)
        
    except ImportError as e:
        app.logger.warning(f"Blueprint import failed (normal during dev): {e}")

    @app.before_request
    def enforce_jwt_auth():
        claims = sync_session_from_jwt()

        if request.path in {'/auth/login', '/user/login'} and request.method == 'GET' and claims:
            return redirect(url_for(role_dashboard_endpoint(claims.get('role'))))

        if not is_protected_path(request.path):
            return None

        if claims:
            return None

        next_path = request.full_path if request.query_string else request.path
        next_path = next_path.rstrip('?')

        if request.path.startswith('/auth/api/'):
            return jsonify({'message': 'Login required', 'error': 'unauthorized'}), 401

        return redirect(url_for('auth_bp.login', next=next_path))
    
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

    @app.after_request
    def add_no_cache_headers(response):
        if should_disable_cache(request.path):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    
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
