import os
from datetime import timedelta
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

# Base directory for the entire project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
IS_PRODUCTION = os.environ.get('ENV') == 'production'

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
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PREFERRED_URL_SCHEME = 'https' if IS_PRODUCTION else 'http'

    # ========================================
    # 2. MYSQL DATABASE SETTINGS 🗄️
    # ========================================
    # These will pull from your .env locally or Render Environment Variables online
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '1234')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'smart_garbage_db')
    MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
    
    # Determine the URI. Using pymysql as it is more compatible with Render/Aiven
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    
    # Legacy connection string for raw MySQL
    MYSQL_CONNECTION_STRING = SQLALCHEMY_DATABASE_URI
    
    # Performance & Security
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 5
    }

    # Add SSL for Aiven Cloud Production
    if IS_PRODUCTION or 'aivencloud.com' in MYSQL_HOST:
        SQLALCHEMY_ENGINE_OPTIONS['connect_args'] = {
            "ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"} # Standard for Render/Debian
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
    JWT_COOKIE_SECURE = IS_PRODUCTION
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_TOKEN_LOCATION = ['cookies', 'headers', 'json']
    JWT_ACCESS_COOKIES = ['access_token']
    JWT_REFRESH_COOKIES = ['refresh_token']
    PROXY_FIX_X_FOR = int(os.environ.get('PROXY_FIX_X_FOR', '1' if IS_PRODUCTION else '0'))
    PROXY_FIX_X_PROTO = int(os.environ.get('PROXY_FIX_X_PROTO', '1' if IS_PRODUCTION else '0'))
    PROXY_FIX_X_HOST = int(os.environ.get('PROXY_FIX_X_HOST', '1' if IS_PRODUCTION else '0'))
    PROXY_FIX_X_PORT = int(os.environ.get('PROXY_FIX_X_PORT', '1' if IS_PRODUCTION else '0'))
    PROXY_FIX_X_PREFIX = int(os.environ.get('PROXY_FIX_X_PREFIX', '0'))

    # CORS Settings
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'http://localhost:3000'
    ]

    # ========================================
    # 6. PRODUCTION SETTINGS ⚙️
    # ========================================
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    JWT_COOKIE_SECURE = False

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    JWT_COOKIE_SECURE = True

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
