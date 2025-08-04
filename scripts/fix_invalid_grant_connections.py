#!/usr/bin/env python3
"""
Script to identify and fix connections with invalid_grant errors.

This script:
1. Identifies connections that might have invalid_grant issues
2. Attempts to refresh tokens to confirm the issue
3. Deactivates problematic connections
4. Provides re-authentication information
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
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
from app.services.xero_auth import XeroAuthService
from app.database.repository import XeroAuthRepository


async def fix_invalid_grant_connections():
    """Identify and fix connections with invalid_grant errors"""
    
    # Get database session
    db = next(get_db())
    repo = XeroAuthRepository(db)
    auth_service = XeroAuthService(repo)
    
    print("🔍 Scanning for connections with potential invalid_grant issues...")
    
    # Get all connections (including inactive ones)
    connections = auth_service.get_all_connections_any_status()
    
    if not connections:
        print("✅ No connections found.")
        return
    
    print(f"📊 Found {len(connections)} total connections")
    
    problematic_connections = []
    successful_connections = []
    
    for i, conn in enumerate(connections, 1):
        print(f"\n[{i}/{len(connections)}] Checking: {conn.tenant_name}")
        print(f"   Tenant ID: {conn.tenant_id}")
        print(f"   App ID: {conn.app_id}")
        print(f"   Expires: {conn.expires_at}")
        
        try:
            # Try to refresh the token
            token_response = await auth_service.refresh_access_token(
                conn.refresh_token,
                conn.app_id,
                tenant_id=conn.tenant_id
            )
            
            # Update connection with new tokens
            auth_service.update_connection_tokens(
                conn.tenant_id,
                token_response,
                conn.app_id
            )
            
            successful_connections.append({
                "tenant_name": conn.tenant_name,
                "tenant_id": conn.tenant_id,
                "app_id": conn.app_id,
                "new_expires_at": token_response.expires_at.isoformat()
            })
            
            print(f"   ✅ Token refreshed successfully")
            print(f"   New expires: {token_response.expires_at}")
            
        except Exception as e:
            error_message = str(e)
            
            if "invalid_grant" in error_message.lower():
                print(f"   ❌ Invalid grant error detected")
                
                # Handle the invalid grant error
                error_info = auth_service.handle_invalid_grant_error(
                    conn.tenant_id,
                    conn.app_id,
                    error_message
                )
                
                problematic_connections.append({
                    "tenant_name": conn.tenant_name,
                    "tenant_id": conn.tenant_id,
                    "app_id": conn.app_id,
                    "error": error_message,
                    "re_auth_url": error_info.get("re_auth_url"),
                    "requires_re_authentication": True
                })
                
                print(f"   🔄 Connection deactivated - requires re-authentication")
                print(f"   Re-auth URL: {error_info.get('re_auth_url')}")
            else:
                print(f"   ⚠️  Other error: {error_message}")
                problematic_connections.append({
                    "tenant_name": conn.tenant_name,
                    "tenant_id": conn.tenant_id,
                    "app_id": conn.app_id,
                    "error": error_message,
                    "requires_re_authentication": False
                })
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 FIX SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully refreshed: {len(successful_connections)}")
    print(f"❌ Problematic connections: {len(problematic_connections)}")
    
    if problematic_connections:
        print("\n🔧 CONNECTIONS REQUIRING RE-AUTHENTICATION:")
        print("-" * 50)
        for conn in problematic_connections:
            print(f"• {conn['tenant_name']} (App {conn['app_id']})")
            if conn.get('re_auth_url'):
                print(f"  Re-auth URL: {conn['re_auth_url']}")
            print(f"  Error: {conn['error']}")
            print()
    
    if successful_connections:
        print("\n✅ SUCCESSFULLY REFRESHED:")
        print("-" * 30)
        for conn in successful_connections:
            print(f"• {conn['tenant_name']} (App {conn['app_id']})")
            print(f"  New expires: {conn['new_expires_at']}")
            print()
    
    # Close database connection
    db.close()


if __name__ == "__main__":
    asyncio.run(fix_invalid_grant_connections()) 