import mysql.connector
from app.config import Config

def get_db():
    """
    Establishes a connection to the MySQL database.
    Includes buffered=True to handle multiple queries in one session.
    """
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            # AUTO-RECONNECT: Keeps the connection alive for long scripts
            autocommit=True, 
            get_warnings=True,
            raise_on_warnings=True
        )
        
        if conn.is_connected():
            return conn
            
    except mysql.connector.Error as err:
        print(f"❌ Database Connection Error: {err}")
        return None

def get_dict_cursor(conn):
    """
    Returns a dictionary cursor. 
    This allows you to access data as 'user['name']' instead of 'user[1]'.
    """
    if conn:
        # dictionary=True is essential for your Login & Dropdown logic
        return conn.cursor(dictionary=True)
    return None

def close_db(conn, cursor=None):
    """
    Safely closes the cursor and connection to save system resources.
    """
    if cursor:
        cursor.close()
    if conn and conn.is_connected():
        conn.close()