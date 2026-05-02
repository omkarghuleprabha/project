#!/usr/bin/env python3
"""
Smart Garbage Management System - Backend Runner
"""
import os
from app import create_app

# 1. Move 'app' out of main so Gunicorn can find it
# 2. Use the 'ENV' environment variable to switch between 'production' and 'development'
env = os.environ.get('ENV', 'development')
app = create_app(env)

def main():
    # Use environment variables for port and host (Render provides these)
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    
    print(f"🚀 Starting Smart Garbage Management API ({env} mode)")
    print(f"📍 Host: http://{host}:{port}")
    print(f"✅ Health: http://{host}:{port}/health")
    
    # Render's FLASK_DEBUG variable will control the debug mode
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(debug=debug_mode, host=host, port=port)

if __name__ == '__main__':
    main()
