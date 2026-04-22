#!/usr/bin/env python3
"""
Smart Garbage Management System - Backend Runner
"""
import os
from app import create_app

def main():
    app = create_app('development')
    
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    
    print(f"🚀 Starting Smart Garbage Management API")
    print(f"📍 Host: http://{host}:{port}")
    print(f"✅ Health: http://{host}:{port}/health")
    
    app.run(debug=True, host=host, port=port)

if __name__ == '__main__':
    main()