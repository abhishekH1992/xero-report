#!/usr/bin/env python3
"""
Database initialization script for Finance Assistant
Run this script to create the database and tables
"""

import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.database import init_db, engine
from app.database.models import Base
from pathlib import Path

def main():
    """Initialize the database"""
    print("🚀 Initializing Finance Assistant Database...")
    
    # Create database directory if it doesn't exist
    db_dir = Path("database")
    db_dir.mkdir(exist_ok=True)
    print(f"📁 Database directory: {db_dir.absolute()}")
    
    try:
        
        # Create all tables with new schema
        print("🏗️  Creating new tables with updated schema...")
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
        
        # Test database connection
        with engine.connect() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in result]
            print(f"📋 Created tables: {', '.join(tables)}")
        
        print("\n🎉 Database initialization completed successfully!")
        print("You can now start the application with: python -m app.main")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 