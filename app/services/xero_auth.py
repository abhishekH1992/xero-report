import secrets
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
import time

from app.config import settings
from app.models.xero_auth import XeroTokenResponse, XeroAuthState
from app.database.repository import XeroAuthRepository
from app.database.models import XeroConnection as DBXeroConnection


class XeroAuthService:
    """Service for handling Xero OAuth2 authentication with database persistence"""
    
    def __init__(self, db_repository: XeroAuthRepository):
        self.client_id = settings.xero_client_id
        self.client_secret = settings.xero_client_secret
        self.redirect_uri = settings.xero_redirect_uri
        self.auth_url = settings.xero_auth_url
        self.token_url = settings.xero_token_url
        self.scope = settings.xero_scope
        self.db_repo = db_repository
    
    def generate_auth_url(self, use_pkce: bool = True) -> tuple[str, XeroAuthState]:
        """
        Generate authorization URL for Xero OAuth2 flow
        
        Args:
            use_pkce: Whether to use PKCE (Proof Key for Code Exchange) for enhanced security
            
        Returns:
            tuple: (authorization_url, auth_state)
        """
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        
        # Generate PKCE code verifier and challenge if enabled
        code_verifier = None
        code_challenge = None
        
        if use_pkce:
            code_verifier = secrets.token_urlsafe(64)
            code_challenge = self._generate_code_challenge(code_verifier)
        
        # Create and store auth state in database
        auth_state = self.db_repo.create_auth_state(state, code_verifier)
        
        # Build authorization URL
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'state': state
        }
        
        if code_challenge:
            params['code_challenge'] = code_challenge
            params['code_challenge_method'] = 'S256'
        
        auth_url = f"{self.auth_url}?{urllib.parse.urlencode(params)}"
        
        return auth_url, auth_state
    
    async def exchange_code_for_tokens(self, code: str, state: str) -> XeroTokenResponse:
        """
        Exchange authorization code for access and refresh tokens
        
        Args:
            code: Authorization code from Xero
            state: State parameter for verification
            
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
            
            # Prepare token request
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
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
                expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
                
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
    
    async def refresh_access_token(self, refresh_token: str, tenant_id: Optional[str] = None) -> XeroTokenResponse:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: The refresh token to use
            tenant_id: Optional tenant ID for logging purposes
            
        Returns:
            XeroTokenResponse: New token response
            
        Raises:
            Exception: If token refresh fails
        """
        start_time = time.time()
        
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
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
                    connection = self.db_repo.get_connection(tenant_id)
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
                expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
                
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
            error_data = e.response.json() if e.response.content else {}
            error_message = error_data.get('error_description', str(e))
            
            # Get connection ID for logging
            connection_id = None
            if tenant_id:
                connection = self.db_repo.get_connection(tenant_id)
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
    
    async def get_tenant_info(self, access_token: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Xero tenant information using access token
        
        Args:
            access_token: Valid access token
            tenant_id: Optional tenant ID for logging purposes
            
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
                
                # Get connection ID for logging
                connection_id = None
                if tenant_id:
                    connection = self.db_repo.get_connection(tenant_id)
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
            if tenant_id:
                connection = self.db_repo.get_connection(tenant_id)
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
    
    def save_connection(self, tenant_id: str, tenant_name: str, token_response: XeroTokenResponse) -> DBXeroConnection:
        """
        Save Xero connection data to database
        
        Args:
            tenant_id: Xero tenant ID
            tenant_name: Xero tenant name
            token_response: Token response from OAuth2 flow
            
        Returns:
            DBXeroConnection: Saved connection data
        """
        if not token_response.expires_at:
            raise ValueError("Token response must have expires_at set")
            
        return self.db_repo.create_connection(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_at=token_response.expires_at,
            scope=token_response.scope
        )
    
    def get_connection(self, tenant_id: str) -> Optional[DBXeroConnection]:
        """Get saved connection by tenant ID from database"""
        return self.db_repo.get_connection(tenant_id)
    
    def get_all_connections(self) -> list[DBXeroConnection]:
        """Get all saved connections from database"""
        return self.db_repo.get_all_connections()
    
    def update_connection_tokens(self, tenant_id: str, token_response: XeroTokenResponse) -> Optional[DBXeroConnection]:
        """Update connection with new tokens in database"""
        if not token_response.expires_at:
            raise ValueError("Token response must have expires_at set")
            
        return self.db_repo.update_connection_tokens(
            tenant_id=tenant_id,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_at=token_response.expires_at,
            scope=token_response.scope
        )
    
    def delete_connection(self, tenant_id: str) -> bool:
        """Delete connection from database"""
        return self.db_repo.delete_connection(tenant_id)
    
    def deactivate_connection(self, tenant_id: str) -> bool:
        """Deactivate connection (soft delete)"""
        return self.db_repo.deactivate_connection(tenant_id)
    
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
    
    def cleanup_expired_states(self) -> int:
        """Clean up expired auth states from database"""
        return self.db_repo.cleanup_expired_states()
    
    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge from code verifier"""
        sha256_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').rstrip('=')
        return code_challenge 