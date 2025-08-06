#!/usr/bin/env python3
"""
Script to add ownership and min_balance columns to xero_connections table
and populate data from ownership_mapping.json
"""

import sys
import os
import json
from pathlib import Path

# Add the parent directory to the Python path to access app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set the database URL to use PostgreSQL
os.environ["DATABASE_URL"] = "postgres://postgres:x8QPDqT2qgqy1ac@127.0.0.1:5432/finance_assistant"

from app.database.database import engine
from app.database.models import XeroConnection
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

def load_ownership_mapping():
    """Load ownership mapping from JSON file"""
    mapping_file = Path("data/ownership_mapping.json")
    if not mapping_file.exists():
        print(f"❌ Ownership mapping file not found: {mapping_file}")
        return {}
    
    try:
        with open(mapping_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading ownership mapping: {e}")
        return {}

def add_columns_to_database():
    """Add ownership and min_balance columns to xero_connections table"""
    try:
        with engine.connect() as conn:
            # Check if columns already exist using PostgreSQL syntax
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'xero_connections' 
                AND column_name IN ('ownership', 'min_balance')
            """))
            existing_columns = [row[0] for row in result]
            
            if 'ownership' not in existing_columns:
                print("➕ Adding ownership column...")
                conn.execute(text("ALTER TABLE xero_connections ADD COLUMN ownership VARCHAR(50)"))
                conn.commit()
                print("✅ ownership column added")
            else:
                print("ℹ️  ownership column already exists")
            
            if 'min_balance' not in existing_columns:
                print("➕ Adding min_balance column...")
                conn.execute(text("ALTER TABLE xero_connections ADD COLUMN min_balance FLOAT"))
                conn.commit()
                print("✅ min_balance column added")
            else:
                print("ℹ️  min_balance column already exists")
                
    except Exception as e:
        print(f"❌ Error adding columns: {e}")
        return False
    
    return True

def update_ownership_data():
    """Update ownership and min_balance data based on tenant_name"""
    ownership_mapping = load_ownership_mapping()
    if not ownership_mapping:
        return False
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get all connections
        connections = session.query(XeroConnection).all()
        print(f"📊 Found {len(connections)} connections in database")
        updated_count = 0
        
        for connection in connections:
            tenant_name = connection.tenant_name.strip()  # Remove extra whitespace
            if tenant_name in ownership_mapping:
                mapping = ownership_mapping[tenant_name]
                
                # Update ownership
                if 'ownership' in mapping:
                    connection.ownership = mapping['ownership']
                
                # Update min_balance
                if 'min_balance' in mapping:
                    connection.min_balance = mapping['min_balance']
                
                updated_count += 1
                print(f"✅ Updated {tenant_name}: ownership={mapping.get('ownership')}, min_balance={mapping.get('min_balance')}")
            else:
                print(f"⚠️  No mapping found for: {tenant_name}")
        
        session.commit()
        print(f"\n🎉 Successfully updated {updated_count} connections")
        
    except Exception as e:
        print(f"❌ Error updating data: {e}")
        session.rollback()
        return False
    finally:
        session.close()
    
    return True

def main():
    """Main function to update database"""
    print("🚀 Starting ownership data update...")
    
    # Step 1: Add columns
    print("\n📋 Step 1: Adding new columns to database...")
    if not add_columns_to_database():
        print("❌ Failed to add columns")
        sys.exit(1)
    
    # Step 2: Update data
    print("\n📋 Step 2: Updating ownership data...")
    if not update_ownership_data():
        print("❌ Failed to update data")
        sys.exit(1)
    
    print("\n🎉 Database update completed successfully!")

if __name__ == "__main__":
    main() 