#!/usr/bin/env python3
"""
Railway deployment startup script for InstaClaw
Handles environment setup and graceful startup
"""

import os
import sys
import time
import signal
from app import app, init_db

def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    print("\n🛑 Shutting down InstaClaw...")
    sys.exit(0)

def main():
    """Main startup function with error handling"""
    print("🦞 InstaClaw Starting Up...")
    
    # Set signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get deployment configuration
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    environment = os.getenv('RAILWAY_ENVIRONMENT', 'local')
    
    print(f"📍 Environment: {environment}")
    print(f"🌐 Binding to: {host}:{port}")
    
    # Initialize database with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"🗄️  Database initialization attempt {attempt + 1}/{max_retries}")
            init_db()
            print("✅ Database ready!")
            break
        except Exception as e:
            print(f"⚠️  Database init attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print("⚠️  Continuing without full database features...")
    
    try:
        print(f"🚀 Starting Flask server on {host}:{port}")
        if environment == "production":
            # Use Gunicorn for production
            import subprocess
            cmd = f"gunicorn app:app --bind {host}:{port} --workers 2 --timeout 120"
            subprocess.run(cmd.split())
        else:
            # Use Flask dev server
            app.run(host=host, port=port, debug=debug, threaded=True)
            
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()