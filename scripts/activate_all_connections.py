#!/usr/bin/env python3
"""
Script to activate all connections by setting is_active = True.

This script:
1. Loads all connections from the database
2. Sets is_active = True for all connections
3. Commits the changes
"""

import sys
import os
from pathlib import Path

# Load .env file before importing app modules
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import get_db
from app.database.repository import XeroAuthRepository


def activate_all_connections():
    """Activate all connections by setting is_active = True"""
    
    # Get database session
    db = next(get_db())
    repo = XeroAuthRepository(db)
    
    print("🔍 Loading all connections from database...")
    
    # Get all connections (including inactive ones)
    connections = repo.get_all_connections_any_status()
    
    if not connections:
        print("✅ No connections found.")
        return
    
    print(f"📊 Found {len(connections)} total connections")
    
    # Count active and inactive connections
    active_count = sum(1 for conn in connections if conn.is_active)
    inactive_count = len(connections) - active_count
    
    print(f"📈 Current status:")
    print(f"   ✅ Active: {active_count}")
    print(f"   ❌ Inactive: {inactive_count}")
    
    if inactive_count == 0:
        print("✅ All connections are already active!")
        return
    
    print(f"\n🔄 Activating {inactive_count} inactive connections...")
    
    # Activate all connections
    activated_count = 0
    for i, conn in enumerate(connections, 1):
        if not conn.is_active:
            print(f"[{i}/{len(connections)}] Activating: {conn.tenant_name} (App {conn.app_id})")
            conn.is_active = True
            activated_count += 1
    
    # Commit changes
    db.commit()
    
    print(f"\n✅ SUCCESS!")
    print(f"📊 Activated {activated_count} connections")
    print(f"📈 All {len(connections)} connections are now active")
    
    # Close database connection
    db.close()


if __name__ == "__main__":
    activate_all_connections() 