from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class XeroTokenResponse(BaseModel):
    """Model for Xero OAuth2 token response"""
    access_token: str = Field(..., description="The access token for API calls")
    refresh_token: str = Field(..., description="The refresh token for getting new access tokens")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    token_type: str = Field(default="Bearer", description="Token type")
    scope: str = Field(..., description="Scopes granted to the application")
    id_token: Optional[str] = Field(None, description="ID token if requested")
    
    # Calculated fields
    expires_at: Optional[datetime] = Field(None, description="Calculated expiration datetime")
    
    def is_expired(self) -> bool:
        """Check if the access token is expired"""
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at


class XeroAuthState(BaseModel):
    """Model for storing OAuth2 state and authorization data"""
    state: str = Field(..., description="OAuth2 state parameter for security")
    code_verifier: Optional[str] = Field(None, description="PKCE code verifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    used: bool = Field(default=False, description="Whether this state has been used")


class XeroConnection(BaseModel):
    """Model for storing Xero connection data"""
    tenant_id: str = Field(..., description="Xero tenant/organization ID")
    tenant_name: str = Field(..., description="Xero tenant/organization name")
    access_token: str = Field(..., description="Current access token")
    refresh_token: str = Field(..., description="Refresh token")
    expires_at: datetime = Field(..., description="Token expiration time")
    scope: str = Field(..., description="Granted scopes")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def is_expired(self) -> bool:
        """Check if the access token is expired"""
        return datetime.utcnow() >= self.expires_at
    
    def needs_refresh(self, buffer_minutes: int = 5) -> bool:
        """Check if token needs refresh (with buffer time)"""
        buffer_time = datetime.utcnow().replace(second=0, microsecond=0)
        buffer_time = buffer_time.replace(minute=buffer_time.minute + buffer_minutes)
        return buffer_time >= self.expires_at 