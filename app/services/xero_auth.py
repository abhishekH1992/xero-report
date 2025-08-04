import secrets
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import httpx
import time

from app.config import settings
from app.models.xero_auth import XeroTokenResponse, XeroAuthState
from app.database.repository import XeroAuthRepository
from app.database.models import XeroConnection as DBXeroConnection
from app.services.xero_app_manager import XeroAppManager


class XeroAuthService:
    """Service for handling Xero OAuth2 authentication with multi-app support"""
    
    def __init__(self, db_repository: XeroAuthRepository):
        self.db_repo = db_repository
        self.app_manager = XeroAppManager()
        # Legacy support
        self.client_id = settings.xero_client_id or settings.xero_app1_client_id
        self.client_secret = settings.xero_client_secret or settings.xero_app1_client_secret
        self.redirect_uri = settings.xero_redirect_uri
        self.auth_url = settings.xero_auth_url
        self.token_url = settings.xero_token_url
        self.scope = settings.xero_scope
    
    def get_app_credentials(self, app_id: int) -> tuple[str, str]:
        """Get client credentials for specific app"""
        try:
            app_config = self.app_manager.get_app_config(app_id)
            client_id = app_config["client_id"]
            client_secret = app_config["client_secret"]
            
            # Validate that credentials are not empty
            if not client_id or not client_secret:
                raise ValueError(f"App {app_id} credentials are empty or not configured")
                
            return client_id, client_secret
        except KeyError as e:
            raise ValueError(f"App {app_id} configuration missing required field: {e}")
        except Exception as e:
            raise ValueError(f"Failed to get app {app_id} credentials: {e}")
    
    def generate_auth_url(self, app_id: int = 1, use_pkce: bool = True) -> tuple[str, XeroAuthState]:
        """
        Generate authorization URL for specific Xero app
        
        Args:
            app_id: Xero app ID (1-2)
            use_pkce: Whether to use PKCE (Proof Key for Code Exchange) for enhanced security
            
        Returns:
            tuple: (authorization_url, auth_state)
        """
        client_id, _ = self.get_app_credentials(app_id)
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        
        # Generate PKCE code verifier and challenge if enabled
        code_verifier = None
        code_challenge = None
        
        if use_pkce:
            code_verifier = secrets.token_urlsafe(64)
            code_challenge = self._generate_code_challenge(code_verifier)
        
        # Create and store auth state in database with app_id
        auth_state = self.db_repo.create_auth_state(state, code_verifier, app_id=app_id)
        
        # Build authorization URL
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'state': state
        }
        
        if code_challenge:
            params['code_challenge'] = code_challenge
            params['code_challenge_method'] = 'S256'
        
        auth_url = f"{self.auth_url}?{urllib.parse.urlencode(params)}"
        
        return auth_url, auth_state
    
    async def exchange_code_for_tokens(self, code: str, state: str, app_id: int = 1) -> XeroTokenResponse:
        """
        Exchange authorization code for access and refresh tokens using specific app
        
        Args:
            code: Authorization code from Xero
            state: State parameter for verification
            app_id: Xero app ID (1-2)
            
        Returns:
            XeroTokenResponse: Token response with access and refresh tokens
            
        Raises:
            ValueError: If state is invalid or already used
            Exception: If token exchange fails
        """
        start_time = time.time()
        
        try:
            # Verify state from database
            auth_state = self.db_repo.get_auth_state(state)
            if not auth_state:
                raise ValueError("Invalid or expired state parameter")
            
            if auth_state.used:
                raise ValueError("State parameter already used")
            
            # Mark state as used
            self.db_repo.mark_auth_state_used(state)
            
            # Get app credentials
            client_id, client_secret = self.get_app_credentials(app_id)
            
            # Prepare token request
            data = {
                'grant_type': 'authorization_code',
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri
            }
            
            # Add PKCE code verifier if used
            if auth_state.code_verifier:
                data['code_verifier'] = auth_state.code_verifier
            
            # Exchange code for tokens
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Log API call
                self.db_repo.log_api_call(
                    connection_id=None,
                    endpoint=self.token_url,
                    method="POST",
                    status_code=response.status_code,
                    response_time_ms=response_time_ms
                )
                
                response.raise_for_status()
                
                token_data = response.json()
                
                # Calculate expiration time
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
                
                # Create token response
                token_response = XeroTokenResponse(
                    access_token=token_data['access_token'],
                    refresh_token=token_data['refresh_token'],
                    expires_in=token_data['expires_in'],
                    token_type=token_data.get('token_type', 'Bearer'),
                    scope=token_data.get('scope', ''),
                    id_token=token_data.get('id_token'),
                    expires_at=expires_at
                )
                
                return token_response
                
        except httpx.HTTPStatusError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            error_data = e.response.json() if e.response.content else {}
            error_message = error_data.get('error_description', str(e))
            
            # Log API error
            self.db_repo.log_api_call(
                connection_id=None,
                endpoint=self.token_url,
                method="POST",
                status_code=e.response.status_code,
                response_time_ms=response_time_ms,
                error_message=error_message
            )
            
            raise Exception(f"Token exchange failed: {error_message}")
    
    async def refresh_access_token(self, refresh_token: str, app_id: int, tenant_id: Optional[str] = None) -> XeroTokenResponse:
        """
        Refresh access token using specific app
        
        Args:
            refresh_token: The refresh token to use
            app_id: Xero app ID (1-2)
            tenant_id: Optional tenant ID for logging purposes
            
        Returns:
            XeroTokenResponse: New token response
            
        Raises:
            Exception: If token refresh fails
        """
        start_time = time.time()
        
        # Get app credentials
        client_id, client_secret = self.get_app_credentials(app_id)
        
        data = {
            'grant_type': 'refresh_token',
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Get connection ID for logging
                connection_id = None
                if tenant_id:
                    connection = self.db_repo.get_connection_by_tenant_and_app(tenant_id, app_id)
                    if connection:
                        connection_id = connection.id
                
                # Log API call
                self.db_repo.log_api_call(
                    connection_id=connection_id,
                    endpoint=self.token_url,
                    method="POST",
                    status_code=response.status_code,
                    response_time_ms=response_time_ms
                )
                
                response.raise_for_status()
                
                token_data = response.json()
                
                # Calculate expiration time
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
                
                # Create token response
                token_response = XeroTokenResponse(
                    access_token=token_data['access_token'],
                    refresh_token=token_data.get('refresh_token', refresh_token),  # Use old refresh token if new one not provided
                    expires_in=token_data['expires_in'],
                    token_type=token_data.get('token_type', 'Bearer'),
                    scope=token_data.get('scope', ''),
                    id_token=token_data.get('id_token'),
                    expires_at=expires_at
                )
                
                return token_response
                
        except httpx.HTTPStatusError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Try to get detailed error information
            error_message = "Unknown error"
            try:
                if e.response.content:
                    error_data = e.response.json()
                    error_message = error_data.get('error_description', error_data.get('error', str(e)))
                else:
                    error_message = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
            except Exception as parse_error:
                error_message = f"HTTP {e.response.status_code}: {e.response.reason_phrase} (Failed to parse response: {str(parse_error)})"
            
            # Get connection ID for logging
            connection_id = None
            if tenant_id:
                connection = self.db_repo.get_connection_by_tenant_and_app(tenant_id, app_id)
                if connection:
                    connection_id = connection.id
            
            # Log API error
            self.db_repo.log_api_call(
                connection_id=connection_id,
                endpoint=self.token_url,
                method="POST",
                status_code=e.response.status_code,
                response_time_ms=response_time_ms,
                error_message=error_message
            )
            
            raise Exception(f"Token refresh failed: {error_message}")
    
    async def get_tenant_info(self, access_token: str, tenant_id: Optional[str] = None, app_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get Xero tenant information using access token
        
        Args:
            access_token: Valid access token
            tenant_id: Optional tenant ID for logging purposes
            app_id: Optional app ID for logging purposes
            
        Returns:
            Dict: Tenant information
        """
        start_time = time.time()
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    'https://api.xero.com/connections',
                    headers=headers
                )
                
                response_time_ms = int((time.time() - start_time) * 1000)

                print(f"🔍 Response: {response.json()}")
                
                # Get connection ID for logging
                connection_id = None
                if tenant_id and app_id:
                    connection = self.db_repo.get_connection_by_tenant_and_app(tenant_id, app_id)
                    if connection:
                        connection_id = connection.id
                
                # Log API call
                self.db_repo.log_api_call(
                    connection_id=connection_id,
                    endpoint='https://api.xero.com/connections',
                    method="GET",
                    status_code=response.status_code,
                    response_time_ms=response_time_ms
                )
                
                response.raise_for_status()
                
                connections = response.json()
                return connections
                
        except httpx.HTTPStatusError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Get connection ID for logging
            connection_id = None
            if tenant_id and app_id:
                connection = self.db_repo.get_connection_by_tenant_and_app(tenant_id, app_id)
                if connection:
                    connection_id = connection.id
            
            # Log API error
            self.db_repo.log_api_call(
                connection_id=connection_id,
                endpoint='https://api.xero.com/connections',
                method="GET",
                status_code=e.response.status_code,
                response_time_ms=response_time_ms,
                error_message=str(e)
            )
            
            raise Exception(f"Failed to get tenant info: {str(e)}")
    
    def save_connection(self, tenant_id: str, tenant_name: str, token_response: XeroTokenResponse, app_id: int = 1) -> DBXeroConnection:
        """
        Save Xero connection data to database with app_id
        
        This method checks if a connection with the given tenant_id and app_id already exists.
        If it exists, it updates the connection with new tokens and information.
        If it doesn't exist, it creates a new connection.
        
        Args:
            tenant_id: Xero tenant ID
            tenant_name: Xero tenant name
            token_response: Token response from OAuth2 flow
            app_id: Xero app ID (1-2)
            
        Returns:
            DBXeroConnection: Saved connection data
        """
        if not token_response.expires_at:
            raise ValueError("Token response must have expires_at set")
        
        # Get business unit for the tenant
        from app.util.business_unit_helper import get_business_unit_for_tenant
        business_type = get_business_unit_for_tenant(tenant_name)
        
        print(f"🏢 Setting business unit for {tenant_name}: {business_type}")
            
        return self.db_repo.upsert_connection(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_at=token_response.expires_at,
            scope=token_response.scope,
            business_type=business_type,
            app_id=app_id
        )
    
    def get_connection(self, tenant_id: str, app_id: Optional[int] = None) -> Optional[DBXeroConnection]:
        """Get saved connection by tenant ID and optionally app_id"""
        if app_id:
            return self.db_repo.get_connection_by_tenant_and_app(tenant_id, app_id)
        return self.db_repo.get_connection(tenant_id)
    
    def get_connection_by_id(self, connection_id: int) -> Optional[DBXeroConnection]:
        """Get connection by database ID"""
        return self.db_repo.get_connection_by_id(connection_id)
    
    def get_all_connections(self) -> list[DBXeroConnection]:
        """Get all active connections"""
        return self.db_repo.get_all_connections()
    
    def get_all_connections_any_status(self) -> list[DBXeroConnection]:
        """Get all connections regardless of active status"""
        return self.db_repo.get_all_connections_any_status()
    
    def get_connections_by_app(self, app_id: int) -> list[DBXeroConnection]:
        """Get all connections for a specific app"""
        return self.db_repo.get_connections_by_app(app_id)
    
    def update_connection_tokens(self, tenant_id: str, token_response: XeroTokenResponse, app_id: int) -> Optional[DBXeroConnection]:
        """Update connection with new tokens in database"""
        if not token_response.expires_at:
            raise ValueError("Token response must have expires_at set")
            
        return self.db_repo.update_connection_tokens(
            tenant_id=tenant_id,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_at=token_response.expires_at,
            scope=token_response.scope,
            app_id=app_id
        )
    
    def delete_connection(self, tenant_id: str, app_id: Optional[int] = None) -> bool:
        """Delete connection from database"""
        return self.db_repo.delete_connection(tenant_id, app_id)
    
    def deactivate_connection(self, tenant_id: str, app_id: Optional[int] = None) -> bool:
        """Deactivate a connection (mark as inactive but don't delete)"""
        return self.db_repo.deactivate_connection(tenant_id, app_id)
    
    def handle_invalid_grant_error(self, tenant_id: str, app_id: int, error_message: str = "Invalid grant error") -> Dict[str, Any]:
        """
        Handle invalid_grant errors by deactivating the connection and providing re-auth info
        
        Args:
            tenant_id: The tenant ID
            app_id: The app ID
            error_message: The error message
            
        Returns:
            Dict with error details and re-auth information
        """
        try:
            # Get connection details before deactivating
            connection = self.get_connection(tenant_id, app_id)
            tenant_name = connection.tenant_name if connection else "Unknown"
            
            # Deactivate the connection
            self.deactivate_connection(tenant_id, app_id)
            
            # Log the error
            self.db_repo.log_api_call(
                connection_id=connection.id if connection else None,
                endpoint="token_refresh",
                method="POST",
                status_code=400,
                response_time_ms=0,
                error_message=f"Invalid grant error - connection deactivated: {error_message}"
            )
            
            return {
                "error": "invalid_grant",
                "message": "The connection has expired and needs to be re-authenticated",
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "app_id": app_id,
                "re_auth_url": f"/api/v1/auth/login/redirect?app_id={app_id}",
                "requires_re_authentication": True
            }
            
        except Exception as e:
            return {
                "error": "invalid_grant",
                "message": f"Failed to handle invalid grant error: {str(e)}",
                "tenant_id": tenant_id,
                "app_id": app_id,
                "requires_re_authentication": True
            }
    
    def get_expired_connections(self, buffer_minutes: int = 5) -> list[DBXeroConnection]:
        """Get connections that need token refresh"""
        return self.db_repo.get_expired_connections(buffer_minutes)
    
    def get_token_history(self, tenant_id: str, limit: int = 10):
        """Get token history for a connection"""
        return self.db_repo.get_token_history(tenant_id, limit)
    
    def get_api_logs(self, tenant_id: Optional[str] = None, limit: int = 50):
        """Get API logs with optional filtering"""
        return self.db_repo.get_api_logs(tenant_id, limit)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return self.db_repo.get_connection_stats()
    
    def get_app_stats(self) -> Dict[int, int]:
        """Get connection count per app"""
        return self.db_repo.get_app_stats()
    
    def cleanup_expired_states(self) -> int:
        """Clean up expired auth states from database"""
        return self.db_repo.cleanup_expired_states()
    
    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge from code verifier"""
        sha256_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').rstrip('=')
        return code_challenge
    
    @classmethod
    def get_service_dependency(cls):
        """FastAPI dependency function for XeroAuthService"""
        from fastapi import Depends
        from sqlalchemy.orm import Session
        from app.database.database import get_db
        from app.database.repository import XeroAuthRepository
        
        def _get_service(db: Session = Depends(get_db)) -> XeroAuthService:
            repo = XeroAuthRepository(db)
            return cls(repo)
        
        return _get_service 