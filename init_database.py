#!/usr/bin/env python3
"""
Database initialization script for Finance Assistant
Run this script to create the database and tables
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database.database import get_db, engine
from app.database.models import Base, XeroAuthState, XeroConnection, XeroTokenHistory, XeroApiLog, ReportQueue

def init_database():
    """Initialize the database with all tables"""
    print("Initializing database...")
    
    # Use the engine from database.py
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("Database tables created successfully!")
    
    # Verify tables exist (SQLite compatible)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        
        tables = [row[0] for row in result]
        print(f"Available tables: {tables}")
        
        # Check if report_queue table exists
        if 'report_queue' in tables:
            print("✅ report_queue table created successfully")
        else:
            print("❌ report_queue table not found")

if __name__ == "__main__":
    init_database() 