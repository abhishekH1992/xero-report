from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

Base = declarative_base()


def utc_now():
    """Return timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)


class XeroAuthState(Base):
    """Database model for OAuth2 state and authorization data"""
    __tablename__ = "xero_auth_states"
    
    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(255), unique=True, index=True, nullable=False)
    code_verifier = Column(String(255), nullable=True)  # For PKCE
    app_id = Column(Integer, nullable=False, default=1)  # Store which app was used
    created_at = Column(DateTime, default=utc_now, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # State expiration
    
    def __repr__(self):
        return f"<XeroAuthState(state={self.state}, used={self.used}, app_id={self.app_id})>"


class XeroConnection(Base):
    """Database model for Xero connection data"""
    __tablename__ = "xero_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(255), index=True, nullable=False)  # Remove unique constraint
    app_id = Column(Integer, nullable=False, default=1, index=True)  # New field
    tenant_name = Column(String(255), nullable=False)
    access_token = Column(Text, nullable=False)  # Encrypted in production
    refresh_token = Column(Text, nullable=False)  # Encrypted in production
    expires_at = Column(DateTime, nullable=False)
    scope = Column(String(500), nullable=False)
    business_type = Column(String(255), default="Commercial Property", nullable=False)
    ownership = Column(String(50), nullable=True)  # fully_owned, partially_owned, not_owned
    min_balance = Column(Float, nullable=True)  # Minimum balance threshold
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Add unique constraint for tenant_id + app_id combination
    __table_args__ = (
        UniqueConstraint('tenant_id', 'app_id', name='uq_tenant_app'),
    )
    
    # Relationship to token history
    token_history = relationship("XeroTokenHistory", back_populates="connection", cascade="all, delete-orphan")
    
    # Relationship to API logs
    api_logs = relationship("XeroApiLog", back_populates="connection", cascade="all, delete-orphan")
    
    # Relationship to accounts
    accounts = relationship("XeroAccount", back_populates="connection", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<XeroConnection(tenant_id={self.tenant_id}, tenant_name={self.tenant_name}, app_id={self.app_id})>"

    @property
    def is_expired(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) >= self.expires_at


class XeroTokenHistory(Base):
    """Database model for tracking token refresh history"""
    __tablename__ = "xero_token_history"
    
    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("xero_connections.id"), nullable=False)
    access_token_hash = Column(String(255), nullable=False)  # Hash of access token for tracking
    refresh_token_hash = Column(String(255), nullable=False)  # Hash of refresh token
    expires_at = Column(DateTime, nullable=False)
    scope = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
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
    created_at = Column(DateTime, default=utc_now, nullable=False)
    
    # Relationship to connection (optional since connection_id can be null)
    connection = relationship("XeroConnection", back_populates="api_logs")
    
    def __repr__(self):
        return f"<XeroApiLog(endpoint={self.endpoint}, status_code={self.status_code})>"


class ReportQueue(Base):
    """Database model for queuing report generation jobs"""
    __tablename__ = "report_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(255), unique=True, index=True, nullable=False)
    job_type = Column(String(100), nullable=False)  # aged_receivables_report, cashflow_report, etc.
    status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    job_data = Column(Text, nullable=False)  # JSON string of job parameters
    result_data = Column(Text, nullable=True)  # JSON string of job results
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ReportQueue(job_id={self.job_id}, type={self.job_type}, status={self.status})>"


class XeroCategory(Base):
    """Model for Xero account categories."""
    __tablename__ = "xero_category"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(100), nullable=True)
    business_type = Column(String(255), nullable=True)
    is_income = Column(Boolean, default=False, nullable=False)  # Indicates if category represents income
    
    # Relationship to accounts
    accounts = relationship("XeroAccount", back_populates="category")
    
    def __repr__(self):
        return f"<XeroCategory(id={self.id}, name='{self.name}', type='{self.type}', is_income={self.is_income})>"


class XeroAccount(Base):
    """Model for Xero accounts linked to categories."""
    __tablename__ = "xero_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("xero_connections.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("xero_category.id"), nullable=False, index=True)
    account_code = Column(String(50), nullable=False, index=True)
    name = Column(String(500), nullable=True)  # Account name/description
    
    # Relationships
    connection = relationship("XeroConnection", back_populates="accounts")
    category = relationship("XeroCategory", back_populates="accounts")
    
    def __repr__(self):
        return f"<XeroAccount(id={self.id}, account_code='{self.account_code}', name='{self.name}')>" 