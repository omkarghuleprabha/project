import mysql.connector
from flask import current_app
import os

def get_db():
    """
    Establishes a connection to the MySQL database.
    Optimized for Aiven Cloud (Render) and Localhost.
    """
    try:
        # 1. Check for the Environment Variable first (Render)
        db_uri = os.environ.get('DATABASE_URL') or current_app.config.get('SQLALCHEMY_DATABASE_URI')
        
        if db_uri and "localhost" not in db_uri:
            # We are on Render/Cloud - Using the Service URI
            # Ensure the prefix is correct for the connector
            if db_uri.startswith("mysql://"):
                db_uri = db_uri.replace("mysql://", "mysql+mysqlconnector://", 1)
            
            conn = mysql.connector.connect(uri=db_uri)
        else:
            # 2. Local fallback for your laptop
            conn = mysql.connector.connect(
                host=current_app.config.get('MYSQL_HOST', 'localhost'),
                user=current_app.config.get('MYSQL_USER', 'root'),
                password=current_app.config.get('MYSQL_PASSWORD', '1234'),
                database=current_app.config.get('MYSQL_DB', 'smart_garbage_db'),
                autocommit=True
            )
        
        if conn.is_connected():
            return conn
            
    except mysql.connector.Error as err:
        # Logging the specific error helps debugging in Render Logs
        print(f"❌ Database Connection Error: {err}")
        return None

def get_dict_cursor(conn):
    """Returns a dictionary cursor for easy data access."""
    if conn and conn.is_connected():
        return conn.cursor(dictionary=True)
    return None

def close_db(conn, cursor=None):
    """Safely closes the database resources."""
    if cursor:
        try:
            cursor.close()
        except:
            pass
    if conn and conn.is_connected():
        conn.close()