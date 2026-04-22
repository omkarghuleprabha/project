from app.utils.db import get_db

conn = get_db()

print("Connected to MySQL")

conn.close()