#!/usr/bin/env python3
"""
Script to refresh all Xero tokens and list out tokens that couldn't be refreshed.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.services.xero_auth import XeroAuthService


async def refresh_all_tokens():
    """Refresh all tokens and report results"""
    db = next(get_db())
    repo = XeroAuthRepository(db)
    auth_service = XeroAuthService(repo)
    
    try:
        # Get all active connections
        connections = repo.get_all_connections()
        
        if not connections:
            print("❌ No active connections found")
            return
        
        print(f"🔄 Found {len(connections)} active connections")
        print("=" * 80)
        
        successful_refreshes = []
        failed_refreshes = []
        
        for i, conn in enumerate(connections, 1):
            print(f"\n[{i}/{len(connections)}] Refreshing token for: {conn.tenant_name}")
            print(f"   Tenant ID: {conn.tenant_id}")
            print(f"   App ID: {conn.app_id}")
            print(f"   Expires: {conn.expires_at}")
            
            try:
                # Attempt to refresh the token
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
                
                successful_refreshes.append({
                    "tenant_name": conn.tenant_name,
                    "tenant_id": conn.tenant_id,
                    "app_id": conn.app_id,
                    "new_expires_at": token_response.expires_at.isoformat()
                })
                
                print(f"   ✅ Successfully refreshed")
                print(f"   New expires: {token_response.expires_at}")
                
            except Exception as e:
                error_message = str(e)
                failed_refreshes.append({
                    "tenant_name": conn.tenant_name,
                    "tenant_id": conn.tenant_id,
                    "app_id": conn.app_id,
                    "error": error_message,
                    "old_expires_at": conn.expires_at.isoformat()
                })
                
                print(f"   ❌ Failed to refresh: {error_message}")
        
        # Print summary
        print("\n" + "=" * 80)
        print("📊 REFRESH SUMMARY")
        print("=" * 80)
        print(f"✅ Successfully refreshed: {len(successful_refreshes)}")
        print(f"❌ Failed to refresh: {len(failed_refreshes)}")
        print(f"📈 Success rate: {(len(successful_refreshes) / len(connections) * 100):.1f}%")
        
        if successful_refreshes:
            print(f"\n✅ SUCCESSFULLY REFRESHED:")
            for refresh in successful_refreshes:
                print(f"   - {refresh['tenant_name']} (App {refresh['app_id']})")
                print(f"     New expires: {refresh['new_expires_at']}")
        
        if failed_refreshes:
            print(f"\n❌ FAILED TO REFRESH:")
            for refresh in failed_refreshes:
                print(f"   - {refresh['tenant_name']} (App {refresh['app_id']})")
                print(f"     Error: {refresh['error']}")
                print(f"     Old expires: {refresh['old_expires_at']}")
        
        # Provide next steps for failed refreshes
        if failed_refreshes:
            print(f"\n🔧 NEXT STEPS FOR FAILED REFRESHES:")
            print(f"1. These connections need re-authentication")
            print(f"2. Use the following commands to fix them:")
            
            # Group by app
            app_1_failures = [r for r in failed_refreshes if r['app_id'] == 1]
            app_2_failures = [r for r in failed_refreshes if r['app_id'] == 2]
            
            if app_1_failures:
                print(f"   - App 1 failures: {len(app_1_failures)}")
                print(f"     Run: python scripts/fix_invalid_token.py <tenant_id> 1")
                for failure in app_1_failures:
                    print(f"       Example: python scripts/fix_invalid_token.py {failure['tenant_id']} 1")
            
            if app_2_failures:
                print(f"   - App 2 failures: {len(app_2_failures)}")
                print(f"     Run: python scripts/fix_invalid_token.py <tenant_id> 2")
                for failure in app_2_failures:
                    print(f"       Example: python scripts/fix_invalid_token.py {failure['tenant_id']} 2")
        
        return {
            "total": len(connections),
            "successful": len(successful_refreshes),
            "failed": len(failed_refreshes),
            "successful_refreshes": successful_refreshes,
            "failed_refreshes": failed_refreshes
        }
        
    except Exception as e:
        print(f"❌ Error refreshing tokens: {str(e)}")
        return None
    finally:
        db.close()


def main():
    """Main function"""
    print("🔄 Starting token refresh for all connections...")
    result = asyncio.run(refresh_all_tokens())
    
    if result:
        print(f"\n🎉 Token refresh process completed!")
        print(f"📊 Final Results:")
        print(f"   Total connections: {result['total']}")
        print(f"   Successfully refreshed: {result['successful']}")
        print(f"   Failed to refresh: {result['failed']}")
    else:
        print(f"\n💥 Token refresh process failed!")


if __name__ == "__main__":
    main() 