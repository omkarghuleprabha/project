#!/usr/bin/env python3
"""Test worker login functionality"""
import sys
sys.path.insert(0, 'd:\\INTERSHIP\\mini project\\smart-garbage-management\\backend')

from app.utils.db import get_db
from werkzeug.security import check_password_hash

# Test credentials from database
test_email = 'omkar.ghule.prabha@gmail.com'
test_phone = '8010465817'
test_password = 'test123'  # This is the password used during registration

print(f"Testing worker login...")
print(f"Email: {test_email}")
print(f"Phone: {test_phone}")

conn = get_db()
if not conn:
    print("ERROR: Cannot connect to database")
    sys.exit(1)

cursor = conn.cursor(dictionary=True)

try:
    # Check if worker exists
    query = "SELECT * FROM village_workers WHERE email = %s OR phone = %s"
    cursor.execute(query, (test_email, test_phone))
    worker = cursor.fetchone()
    
    if worker:
        print(f"\nWorker found:")
        print(f"  ID: {worker['id']}")
        print(f"  Name: {worker['name']}")
        print(f"  Email: {worker['email']}")
        print(f"  Phone: {worker['phone']}")
        print(f"  Status: {worker['status']}")
        print(f"  Password hash: {worker['password'][:50]}...")
        
        # Try to verify the password
        print(f"\nTesting password verification with password: '{test_password}'")
        try:
            result = check_password_hash(worker['password'], test_password)
            print(f"Password verification result: {result}")
        except Exception as e:
            print(f"Error during password check: {e}")
    else:
        print(f"ERROR: No worker found with email {test_email} or phone {test_phone}")
        
        # List all workers
        print("\nAvailable workers in database:")
        cursor.execute("SELECT id, name, email, phone FROM village_workers")
        all_workers = cursor.fetchall()
        for w in all_workers:
            print(f"  - {w['name']} ({w['email']}, {w['phone']})")
            
except Exception as e:
    print(f"Database error: {e}")
    import traceback
    traceback.print_exc()
finally:
    cursor.close()
    conn.close()
