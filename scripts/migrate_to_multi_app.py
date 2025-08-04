#!/usr/bin/env python3
"""
Migration script to add app_id to existing xero_connections and xero_auth_states
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.config import settings

# Import the database URL directly from the database module
from app.database.database import SQLALCHEMY_DATABASE_URL


def migrate_to_multi_app():
    """Migrate existing connections to multi-app structure"""
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if app_id column exists in xero_connections using SQLite pragma
        result = conn.execute(text("PRAGMA table_info(xero_connections)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'app_id' not in columns:
            print("Adding app_id column to xero_connections...")
            conn.execute(text("""
                ALTER TABLE xero_connections 
                ADD COLUMN app_id INTEGER NOT NULL DEFAULT 1
            """))
            
            # print("Setting app_id = 1 for all existing records in xero_connections...")
            # conn.execute(text("""
            #     UPDATE xero_connections 
            #     SET app_id = 1 
            #     WHERE app_id IS NULL OR app_id = 0
            # """))
            
            print("Creating indexes for xero_connections...")
            conn.execute(text("""
                CREATE INDEX idx_xero_connections_app_id 
                ON xero_connections(app_id)
            """))
            
            conn.execute(text("""
                CREATE INDEX idx_xero_connections_tenant_app 
                ON xero_connections(tenant_id, app_id)
            """))
            
            # Add unique constraint for tenant_id + app_id combination
            try:
                conn.execute(text("""
                    CREATE UNIQUE INDEX uq_tenant_app 
                    ON xero_connections(tenant_id, app_id)
                """))
                print("Added unique constraint for tenant_id + app_id")
            except Exception as e:
                print(f"Warning: Could not add unique constraint: {e}")
            
            # Verify the migration
            result = conn.execute(text("""
                SELECT COUNT(*) as total_records,
                       COUNT(CASE WHEN app_id = 1 THEN 1 END) as app_1_records
                FROM xero_connections
            """))
            
            stats = result.fetchone()
            print(f"xero_connections migration completed successfully!")
            print(f"Total records: {stats[0]}")
            print(f"Records with app_id = 1: {stats[1]}")
            
        else:
            print("app_id column already exists in xero_connections. Checking existing data...")
            
            # Check if there are any records with NULL or 0 app_id
            result = conn.execute(text("""
                SELECT COUNT(*) as null_records
                FROM xero_connections 
                WHERE app_id IS NULL OR app_id = 0
            """))
            
            null_count = result.fetchone()[0]
            
            if null_count > 0:
                print(f"Found {null_count} records with NULL or 0 app_id. Updating to app_id = 1...")
                conn.execute(text("""
                    UPDATE xero_connections 
                    SET app_id = 1 
                    WHERE app_id IS NULL OR app_id = 0
                """))
                print("Updated existing records to app_id = 1")
            else:
                print("All existing records already have valid app_id values")
        
        # Check if app_id column exists in xero_auth_states
        result = conn.execute(text("PRAGMA table_info(xero_auth_states)"))
        auth_columns = [row[1] for row in result.fetchall()]
        
        if 'app_id' not in auth_columns:
            print("Adding app_id column to xero_auth_states...")
            conn.execute(text("""
                ALTER TABLE xero_auth_states 
                ADD COLUMN app_id INTEGER NOT NULL DEFAULT 1
            """))
            
            print("Setting app_id = 1 for all existing records in xero_auth_states...")
            conn.execute(text("""
                UPDATE xero_auth_states 
                SET app_id = 1 
                WHERE app_id IS NULL OR app_id = 0
            """))
            
            print("xero_auth_states migration completed successfully!")
        else:
            print("app_id column already exists in xero_auth_states")
            
            # Check if there are any records with NULL or 0 app_id
            result = conn.execute(text("""
                SELECT COUNT(*) as null_records
                FROM xero_auth_states 
                WHERE app_id IS NULL OR app_id = 0
            """))
            
            null_count = result.fetchone()[0]
            
            if null_count > 0:
                print(f"Found {null_count} auth state records with NULL or 0 app_id. Updating to app_id = 1...")
                conn.execute(text("""
                    UPDATE xero_auth_states 
                    SET app_id = 1 
                    WHERE app_id IS NULL OR app_id = 0
                """))
                print("Updated existing auth state records to app_id = 1")
            else:
                print("All existing auth state records already have valid app_id values")
        
        # Show current statistics
        result = conn.execute(text("""
            SELECT app_id, COUNT(*) as count
            FROM xero_connections
            GROUP BY app_id
            ORDER BY app_id
        """))
        
        print("\nCurrent app distribution:")
        for row in result.fetchall():
            print(f"  App {row[0]}: {row[1]} connections")


if __name__ == "__main__":
    migrate_to_multi_app() 