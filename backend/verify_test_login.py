#!/usr/bin/env python3
"""Verify worker login with test credentials"""
import sys
sys.path.insert(0, 'd:\\INTERSHIP\\mini project\\smart-garbage-management\\backend')

from app.utils.db import get_db
from werkzeug.security import check_password_hash

# Test credentials
test_email = 'worker@test.com'
test_password = 'worker123'

print(f"Testing worker login...")
print(f"Email: {test_email}")
print(f"Password: {test_password}")

conn = get_db()
if not conn:
    print("ERROR: Cannot connect to database")
    sys.exit(1)

cursor = conn.cursor(dictionary=True)

try:
    # Simulate login query
    query = "SELECT * FROM village_workers WHERE email = %s OR phone = %s"
    cursor.execute(query, (test_email, test_email))
    worker = cursor.fetchone()
    
    if worker:
        print(f"\n✓ Worker found: {worker['name']}")
        print(f"  ID: {worker['id']}")
        print(f"  Email: {worker['email']}")
        print(f"  Status: {worker['status']}")
        
        # Verify password
        if check_password_hash(worker['password'], test_password):
            print(f"\n✓ Password verification: PASSED")
            print(f"\nLogin would succeed with:")
            print(f"  session['user_id'] = {worker['id']}")
            print(f"  session['user_name'] = {worker['name']}")
            print(f"  session['role'] = 'worker'")
            print(f"\nRedirect to: /worker-dashboard")
        else:
            print(f"\n✗ Password verification: FAILED")
    else:
        print(f"\n✗ Worker not found")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    cursor.close()
    conn.close()
