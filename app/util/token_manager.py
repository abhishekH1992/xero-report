from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException

from app.database.models import XeroConnection
from app.services.xero_auth import XeroAuthService


class TokenManager:
    """Centralized token management utility for handling app-specific token refresh"""
    
    def __init__(self, xero_auth_service: XeroAuthService):
        self.xero_auth_service = xero_auth_service
    
    async def ensure_valid_token(
        self, 
        connection: XeroConnection, 
        tenant_id: str, 
        app_id: Optional[int] = None,
        buffer_minutes: int = 5
    ) -> XeroConnection:
        """
        Ensure the connection has a valid token, refresh if needed using app-specific credentials.
        
        Args:
            connection: The Xero connection
            tenant_id: The tenant ID
            app_id: The app ID (optional, defaults to connection.app_id)
            buffer_minutes: Minutes before expiry to consider token as needing refresh
            
        Returns:
            Updated connection with valid tokens
            
        Raises:
            HTTPException: If token refresh fails
        """
        # Use connection.app_id if app_id not provided
        target_app_id = app_id or connection.app_id
        
        # Check if token is expired or about to expire
        buffer_time = datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes)
        
        if connection.expires_at <= buffer_time:
            try:
                # Manually refresh the token using app-specific credentials
                token_response = await self.xero_auth_service.refresh_access_token(
                    connection.refresh_token,
                    target_app_id,
                    tenant_id=tenant_id
                )
                
                # Update connection with new tokens
                updated_connection = self.xero_auth_service.update_connection_tokens(
                    tenant_id, 
                    token_response, 
                    target_app_id
                )
                
                if not updated_connection:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Failed to update connection after token refresh for tenant {tenant_id}, app {target_app_id}"
                    )
                
                return updated_connection
                    
            except Exception as e:
                error_message = str(e)
                
                # Handle invalid_grant errors specifically
                if "invalid_grant" in error_message.lower():
                    raise HTTPException(
                        status_code=401, 
                        detail={
                            "error": "invalid_grant",
                            "message": "Authentication token has expired and needs to be refreshed",
                            "requires_re_authentication": True,
                            "tenant_id": tenant_id,
                            "app_id": target_app_id,
                            "re_auth_url": f"/api/v1/auth/login/redirect?app_id={target_app_id}"
                        }
                    )
                else:
                    raise HTTPException(
                        status_code=500, 
                        detail=f"Failed to refresh token for tenant {tenant_id}, app {target_app_id}: {error_message}"
                    )
        
        return connection
    
    def is_token_valid(self, connection: XeroConnection, buffer_minutes: int = 5) -> bool:
        """
        Check if a token is valid (not expired or about to expire)
        
        Args:
            connection: The Xero connection
            buffer_minutes: Minutes before expiry to consider token as invalid
            
        Returns:
            True if token is valid, False otherwise
        """
        buffer_time = datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes)
        return connection.expires_at > buffer_time
    
    def get_token_status(self, connection: XeroConnection) -> dict:
        """
        Get detailed token status information
        
        Args:
            connection: The Xero connection
            
        Returns:
            Dictionary with token status information
        """
        now = datetime.now(timezone.utc)
        expires_in = (connection.expires_at - now).total_seconds()
        
        return {
            "is_valid": self.is_token_valid(connection),
            "expires_at": connection.expires_at.isoformat(),
            "expires_in_seconds": int(expires_in),
            "expires_in_minutes": int(expires_in / 60),
            "app_id": connection.app_id,
            "tenant_id": connection.tenant_id,
            "tenant_name": connection.tenant_name
        } 