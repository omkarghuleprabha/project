import os
from datetime import timedelta

# Base directory for the entire project
BASE_DIR = r"D:\INTERSHIP\Garbage Management System\Garbage Management System\smart-garbage-management"

class Config:
    # ========================================
    # 1. SECURITY SETTINGS 🔒
    # ========================================
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'smart-garbage-dev-key-2026-change-in-production'
    
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'smart-garbage-jwt-secret-2026-super-secure-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=90)
    
    # Session Security
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('ENV') == 'production'

    # ========================================
    # 2. MYSQL DATABASE SETTINGS 🗄️
    # ========================================
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '1234')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'smart_garbage_db')
    
    # SQLAlchemy URI for Flask-SQLAlchemy
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+mysqlconnector://"
        f"{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
        f"?charset=utf8mb4"
    )
    
    # Legacy connection string for raw MySQL (get_db() function)
    MYSQL_CONNECTION_STRING = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    
    # Performance & Security
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 20,
        'max_overflow': 10
    }

    # ========================================
    # 3. FILE UPLOAD SETTINGS 📁
    # ========================================
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'backend', 'app', 'static', 'uploads')
    UPLOAD_FOLDER_URL = '/static/uploads'
    
    # File size limits (16MB max)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Allowed file extensions for garbage photos
    ALLOWED_EXTENSIONS = {
        'images': {'.jpg', '.jpeg', '.png', '.gif', '.webp'},
        'documents': {'.pdf', '.doc', '.docx'}
    }
    
    # Max files per request
    MAX_FILES_PER_REQUEST = 5

    # ========================================
    # 4. PATH CONFIGURATION 🛤️
    # ========================================
    BASE_DIR = BASE_DIR
    TEMPLATES_DIR = os.path.join(BASE_DIR, 'backend', 'app', 'templates')
    STATIC_DIR = os.path.join(BASE_DIR, 'backend', 'app', 'static')
    
    # Logs
    LOG_DIR = os.path.join(BASE_DIR, 'backend', 'logs')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # ========================================
    # 5. JWT & API SETTINGS 🔐
    # ========================================
    JWT_COOKIE_SECURE = os.environ.get('ENV') == 'production'
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_TOKEN_LOCATION = ['cookies', 'headers', 'json']
    JWT_ACCESS_COOKIES = ['access_token']
    JWT_REFRESH_COOKIES = ['refresh_token']

    # CORS Settings
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'http://localhost:3000'  # React dev server
    ]

    # ========================================
    # 6. PRODUCTION SETTINGS ⚙️
    # ========================================
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = 'redis://localhost:6379/0'

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    JWT_COOKIE_SECURE = False

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    JWT_COOKIE_SECURE = True
    
    # Use environment variables in production
    MYSQL_HOST = os.environ.get('MYSQL_HOST')
    MYSQL_USER = os.environ.get('MYSQL_USER')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
    MYSQL_DB = os.environ.get('MYSQL_DB')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

# Config selection
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}