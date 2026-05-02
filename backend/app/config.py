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
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or '1234'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'smart_garbage_db'
    
    # CRITICAL FIX: Detect and ignore empty strings from Render environment
    _raw_port = os.environ.get('MYSQL_PORT')
    MYSQL_PORT = _raw_port if (_raw_port and _raw_port.strip()) else '3306'
    
    # SQLAlchemy URI
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    
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
            "ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"} 
        }

    # ========================================
    # 3. FILE UPLOAD SETTINGS 📁
    # ========================================
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'backend', 'app', 'static', 'uploads')
    UPLOAD_FOLDER_URL = '/static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 
    ALLOWED_EXTENSIONS = {
        'images': {'.jpg', '.jpeg', '.png', '.gif', '.webp'},
        'documents': {'.pdf', '.doc', '.docx'}
    }
    MAX_FILES_PER_REQUEST = 5

    # ========================================
    # 4. PATH CONFIGURATION 🛤️
    # ========================================
    BASE_DIR = BASE_DIR
    TEMPLATES_DIR = os.path.join(BASE_DIR, 'backend', 'app', 'templates')
    STATIC_DIR = os.path.join(BASE_DIR, 'backend', 'app', 'static')
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
    
    @staticmethod
    def get_int_env(key, default):
        try:
            val = os.environ.get(key)
            return int(val) if (val and val.strip()) else default
        except (ValueError, TypeError):
            return default

    # These use the static method to safely parse integers
    PROXY_FIX_X_FOR = 1 if IS_PRODUCTION else 0
    PROXY_FIX_X_PROTO = 1 if IS_PRODUCTION else 0
    PROXY_FIX_X_HOST = 1 if IS_PRODUCTION else 0
    PROXY_FIX_X_PORT = 1 if IS_PRODUCTION else 0
    PROXY_FIX_X_PREFIX = 0

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

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
