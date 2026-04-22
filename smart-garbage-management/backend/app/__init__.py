import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Load config from config.py
    from .config import Config
    app.config.from_object(Config)

    # SSL CONFIGURATION FOR AIVEN (Essential for Cloud)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "connect_args": {
            "ssl_verify_cert": False,
            "ssl_verify_identity": False
        }
    }

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    CORS(app)

    login_manager.login_view = 'auth_bp.login'

    # REGISTER BLUEPRINTS
    from .routes.auth_routes import auth_bp
    from .routes.admin_routes import admin_bp
    from .routes.user_routes import user_bp
    from .routes.main_routes import main_bp
    from .routes.api_routes import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(api_bp)

    # AUTO-CREATE TABLES ON DEPLOYMENT
    with app.app_context():
        try:
            db.create_all()
            print("🚀 Successfully connected to Aiven Cloud Database!")
        except Exception as e:
            print(f"❌ Database Error: {e}")

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models.user_model import User
    return db.session.get(User, int(user_id))