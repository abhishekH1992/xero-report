#!/usr/bin/env python3
"""
Script to update business units for existing Xero connections based on company data.
This script reads the company_business_units.json file and updates the business_type
field for all existing connections in the database.
"""

import json
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.database.database import get_db
from app.database.models import XeroConnection
from sqlalchemy.orm import Session


def load_company_data():
    """Load company business units data from JSON file"""
    json_file = Path(__file__).parent / "company_business_units.json"
    
    if not json_file.exists():
        print(f"❌ Error: {json_file} not found")
        return None
    
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON file: {e}")
        return None
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
        return None


def update_business_units():
    """Update business units for all existing connections"""
    company_data = load_company_data()
    if not company_data:
        return False
    
    db = next(get_db())
    
    try:
        # Get all existing connections
        connections = db.query(XeroConnection).filter(XeroConnection.is_active == True).all()
        
        if not connections:
            print("ℹ️  No active connections found in database")
            return True
        
        print(f"📊 Found {len(connections)} active connections")
        
        updated_count = 0
        not_found_count = 0
        
        for connection in connections:
            tenant_name = connection.tenant_name.strip()  # Trim whitespace from database value
            
            if tenant_name in company_data:
                new_business_unit = company_data[tenant_name]
                
                if connection.business_type != new_business_unit:
                    print(f"🔄 Updating {tenant_name}: {connection.business_type} → {new_business_unit}")
                    connection.business_type = new_business_unit
                    updated_count += 1
                else:
                    print(f"✅ {tenant_name}: Already has correct business unit ({new_business_unit})")
            else:
                print(f"⚠️  {tenant_name}: Not found in company data")
                not_found_count += 1
        
        # Commit changes
        db.commit()
        
        print(f"\n📈 Summary:")
        print(f"   ✅ Updated: {updated_count} connections")
        print(f"   ⚠️  Not found: {not_found_count} connections")
        print(f"   📊 Total processed: {len(connections)} connections")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating business units: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main():
    """Main function"""
    print("🚀 Starting business unit update script...")
    
    success = update_business_units()
    
    if success:
        print("✅ Business unit update completed successfully!")
    else:
        print("❌ Business unit update failed!")
        sys.exit(1)


if __name__ == "__main__":
    main() 