#!/usr/bin/env python3
"""Create a test worker with known credentials"""
import sys
sys.path.insert(0, 'd:\\INTERSHIP\\mini project\\smart-garbage-management\\backend')

from app.utils.db import get_db
from werkzeug.security import generate_password_hash
import mysql.connector

conn = get_db()
if not conn:
    print("ERROR: Cannot connect to database")
    sys.exit(1)

cursor = conn.cursor(dictionary=True)

try:
    # Delete existing test worker if present
    cursor.execute("DELETE FROM village_workers WHERE email = 'worker@test.com'")
    conn.commit()
    print("Cleaned up old test worker")
    
    # Create new test worker
    test_password = "worker123"
    hashed_password = generate_password_hash(test_password)
    
    # Using village_id = 1 (from existing data)
    query = """
        INSERT INTO village_workers (name, email, phone, password, village_id, status) 
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, ('Test Worker', 'worker@test.com', '9999999999', hashed_password, 1, 'Active'))
    conn.commit()
    
    print(f"\n✓ Test worker created successfully!")
    print(f"\nLogin Credentials:")
    print(f"  Email: worker@test.com")
    print(f"  Phone: 9999999999")
    print(f"  Password: {test_password}")
    print(f"\nPassword hash (for verification): {hashed_password}")
    
except mysql.connector.Error as e:
    print(f"Database error: {e}")
    import traceback
    traceback.print_exc()
finally:
    cursor.close()
    conn.close()
