from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class XeroAuthState(Base):
    """Database model for OAuth2 state and authorization data"""
    __tablename__ = "xero_auth_states"
    
    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(255), unique=True, index=True, nullable=False)
    code_verifier = Column(String(255), nullable=True)  # For PKCE
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # State expiration
    
    def __repr__(self):
        return f"<XeroAuthState(state={self.state}, used={self.used})>"


class XeroConnection(Base):
    """Database model for Xero connection data"""
    __tablename__ = "xero_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(255), unique=True, index=True, nullable=False)
    tenant_name = Column(String(255), nullable=False)
    access_token = Column(Text, nullable=False)  # Encrypted in production
    refresh_token = Column(Text, nullable=False)  # Encrypted in production
    expires_at = Column(DateTime, nullable=False)
    scope = Column(String(500), nullable=False)
    business_type = Column(String(255), default="Commercial Properties", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationship to token history
    token_history = relationship("XeroTokenHistory", back_populates="connection", cascade="all, delete-orphan")
    
    # Relationship to API logs
    api_logs = relationship("XeroApiLog", back_populates="connection", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<XeroConnection(tenant_id={self.tenant_id}, tenant_name={self.tenant_name})>"

    @property
    def is_expired(self):
        from datetime import datetime
        return datetime.utcnow() >= self.expires_at


class XeroTokenHistory(Base):
    """Database model for tracking token refresh history"""
    __tablename__ = "xero_token_history"
    
    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("xero_connections.id"), nullable=False)
    access_token_hash = Column(String(255), nullable=False)  # Hash of access token for tracking
    refresh_token_hash = Column(String(255), nullable=False)  # Hash of refresh token
    expires_at = Column(DateTime, nullable=False)
    scope = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    refresh_type = Column(String(50), nullable=False)  # 'initial', 'refresh', 'renewal'
    old_token_hash = Column(String(255), nullable=True)
    new_token_hash = Column(String(255), nullable=False)
    
    # Relationship to connection
    connection = relationship("XeroConnection", back_populates="token_history")
    
    def __repr__(self):
        return f"<XeroTokenHistory(connection_id={self.connection_id}, refresh_type={self.refresh_type})>"


class XeroApiLog(Base):
    """Database model for logging API calls and errors"""
    __tablename__ = "xero_api_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("xero_connections.id"), nullable=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship to connection (optional since connection_id can be null)
    connection = relationship("XeroConnection", back_populates="api_logs")
    
    def __repr__(self):
        return f"<XeroApiLog(endpoint={self.endpoint}, status_code={self.status_code})>" 