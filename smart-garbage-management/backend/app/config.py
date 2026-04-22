import os

class Config:
    # 1. Security Setting
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-12345'

    # 2. Database Connection Logic
    # Automatically detects Render's environment variable
    DATABASE_URL = os.environ.get('DATABASE_URL')

    if DATABASE_URL:
        # Fix for Render: SQLAlchemy requires 'mysql+mysqlconnector'
        if DATABASE_URL.startswith("mysql://"):
            SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace("mysql://", "mysql+mysqlconnector://", 1)
        else:
            SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        # Local laptop settings (fallback)
        MYSQL_HOST = 'localhost'
        MYSQL_USER = 'root'
        MYSQL_PASSWORD = '1234'
        MYSQL_DB = 'smart_garbage_db'
        SQLALCHEMY_DATABASE_URI = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"

    # 3. SQLAlchemy Configuration
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 4. Upload Settings
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB limit