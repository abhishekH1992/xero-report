from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Optional, List, Dict, Any

from .models import XeroAuthState, XeroConnection, XeroTokenHistory, XeroApiLog


class XeroAuthRepository:
    """Repository for handling Xero authentication database operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # Auth State Operations
    def create_auth_state(self, state: str, code_verifier: Optional[str] = None, 
                         expires_in_hours: int = 1, app_id: int = 1) -> XeroAuthState:
        """Create a new OAuth2 auth state with app_id"""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
        
        auth_state = XeroAuthState(
            state=state,
            code_verifier=code_verifier,
            app_id=app_id,
            expires_at=expires_at
        )
        
        self.db.add(auth_state)
        self.db.commit()
        self.db.refresh(auth_state)
        return auth_state
    
    def get_auth_state(self, state: str) -> Optional[XeroAuthState]:
        """Get auth state by state parameter"""
        return self.db.query(XeroAuthState).filter(
            and_(
                XeroAuthState.state == state,
                XeroAuthState.expires_at > datetime.now(timezone.utc)
            )
        ).first()
    
    def mark_auth_state_used(self, state: str) -> bool:
        """Mark auth state as used"""
        auth_state = self.db.query(XeroAuthState).filter(
            XeroAuthState.state == state
        ).first()
        
        if auth_state:
            auth_state.used = True
            self.db.commit()
            return True
        return False
    
    def cleanup_expired_states(self) -> int:
        """Clean up expired auth states and return count of deleted records"""
        expired_states = self.db.query(XeroAuthState).filter(
            or_(
                XeroAuthState.expires_at <= datetime.now(timezone.utc),
                XeroAuthState.used == True
            )
        ).all()
        
        count = len(expired_states)
        for state in expired_states:
            self.db.delete(state)
        
        self.db.commit()
        return count
    
    # Connection Operations
    def create_connection(self, tenant_id: str, tenant_name: str, 
                         access_token: str, refresh_token: str,
                         expires_at: datetime, scope: str, 
                         business_type: str = "Commercial Property", app_id: int = 1) -> XeroConnection:
        """Create a new Xero connection with app_id"""
        connection = XeroConnection(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
            business_type=business_type,
            app_id=app_id
        )
        
        self.db.add(connection)
        self.db.commit()
        self.db.refresh(connection)
        
        # Log token history
        self._log_token_history(connection, access_token, refresh_token, 
                               expires_at, scope, "initial")
        
        return connection
    
    def get_connection(self, tenant_id: str) -> Optional[XeroConnection]:
        """Get active connection by tenant ID (legacy method - returns first match)"""
        return self.db.query(XeroConnection).filter(
            and_(
                XeroConnection.tenant_id == tenant_id,
                XeroConnection.is_active == True
            )
        ).first()
    
    def get_connection_by_tenant_and_app(self, tenant_id: str, app_id: int) -> Optional[XeroConnection]:
        """Get connection by tenant ID and app ID"""
        return self.db.query(XeroConnection).filter(
            and_(
                XeroConnection.tenant_id == tenant_id,
                XeroConnection.app_id == app_id,
                XeroConnection.is_active == True
            )
        ).first()
    
    def get_connections_by_app(self, app_id: int) -> List[XeroConnection]:
        """Get all connections for a specific app"""
        return self.db.query(XeroConnection).filter(
            and_(
                XeroConnection.app_id == app_id,
                XeroConnection.is_active == True
            )
        ).all()
    
    def get_connection_any_status(self, tenant_id: str) -> Optional[XeroConnection]:
        """Get connection by tenant ID regardless of active status"""
        return self.db.query(XeroConnection).filter(
            XeroConnection.tenant_id == tenant_id
        ).first()
    
    def get_all_connections(self) -> List[XeroConnection]:
        """Get all active connections"""
        return self.db.query(XeroConnection).filter(
            XeroConnection.is_active == True
        ).all()
    
    def get_all_connections_any_status(self) -> List[XeroConnection]:
        """Get all connections regardless of active status"""
        return self.db.query(XeroConnection).all()
    
    def update_connection_tokens(self, tenant_id: str, access_token: str, 
                                refresh_token: str, expires_at: datetime, 
                                scope: str, app_id: int = 1) -> Optional[XeroConnection]:
        """Update connection with new tokens using app_id"""
        connection = self.get_connection_by_tenant_and_app(tenant_id, app_id)
        
        if connection:
            old_token_hash = hashlib.sha256(connection.access_token.encode()).hexdigest()
            connection.access_token = access_token
            connection.refresh_token = refresh_token
            connection.expires_at = expires_at
            connection.scope = scope
            connection.updated_at = datetime.now(timezone.utc)
            
            self.db.commit()
            self.db.refresh(connection)
            
            # Log token history
            self._log_token_history(connection, access_token, refresh_token, 
                                   expires_at, scope, "refresh", old_token_hash=old_token_hash)
            
            return connection
        return None
    
    def upsert_connection(self, tenant_id: str, tenant_name: str, 
                         access_token: str, refresh_token: str,
                         expires_at: datetime, scope: str,
                         business_type: str = "Commercial Property", app_id: int = 1) -> XeroConnection:
        """
        Upsert connection - update if exists, create if not
        
        Args:
            tenant_id: Xero tenant ID
            tenant_name: Xero tenant name
            access_token: Current access token
            refresh_token: Refresh token
            expires_at: Token expiration time
            scope: Granted scopes
            app_id: Xero app ID (1-2)
            
        Returns:
            XeroConnection: The upserted connection
        """
        # Check if connection exists for this tenant and app (regardless of active status)
        existing_connection = self.db.query(XeroConnection).filter(
            and_(
                XeroConnection.tenant_id == tenant_id,
                XeroConnection.app_id == app_id
            )
        ).first()
        
        if existing_connection:
            old_token_hash = hashlib.sha256(existing_connection.access_token.encode()).hexdigest()
            # Update existing connection
            existing_connection.tenant_name = tenant_name
            existing_connection.access_token = access_token
            existing_connection.refresh_token = refresh_token
            existing_connection.expires_at = expires_at
            existing_connection.scope = scope
            existing_connection.business_type = business_type
            existing_connection.updated_at = datetime.now(timezone.utc)
            existing_connection.is_active = True  # Reactivate if it was deactivated
            
            self.db.commit()
            self.db.refresh(existing_connection)
            
            # Log token history
            self._log_token_history(existing_connection, access_token, refresh_token, 
                                   expires_at, scope, "upsert_update", old_token_hash=old_token_hash)
            
            return existing_connection
        else:
            # Create new connection
            return self.create_connection(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope,
                business_type=business_type,
                app_id=app_id
            )
    
    def deactivate_connection(self, tenant_id: str, app_id: Optional[int] = None) -> bool:
        """Deactivate a connection (soft delete)"""
        if app_id:
            connection = self.get_connection_by_tenant_and_app(tenant_id, app_id)
        else:
            connection = self.get_connection(tenant_id)
        
        if connection:
            connection.is_active = False
            connection.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            return True
        return False
    
    def delete_connection(self, tenant_id: str, app_id: Optional[int] = None) -> bool:
        """Hard delete a connection and all related records"""
        if app_id:
            connection = self.db.query(XeroConnection).filter(
                and_(
                    XeroConnection.tenant_id == tenant_id,
                    XeroConnection.app_id == app_id
                )
            ).first()
        else:
            connection = self.db.query(XeroConnection).filter(
                XeroConnection.tenant_id == tenant_id
            ).first()
        
        if connection:
            # Delete related token history records first
            self.db.query(XeroTokenHistory).filter(
                XeroTokenHistory.connection_id == connection.id
            ).delete()
            
            # Delete related API log records
            self.db.query(XeroApiLog).filter(
                XeroApiLog.connection_id == connection.id
            ).delete()
            
            # Delete the connection
            self.db.delete(connection)
            self.db.commit()
            return True
        return False
    
    def get_expired_connections(self, buffer_minutes: int = 5) -> List[XeroConnection]:
        """Get connections that need token refresh, grouped by app"""
        buffer_time = datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes)
        
        return self.db.query(XeroConnection).filter(
            and_(
                XeroConnection.expires_at <= buffer_time,
                XeroConnection.is_active == True
            )
        ).all()
    
    def get_app_stats(self) -> Dict[int, int]:
        """Get connection count per app"""
        stats = {}
        for app_id in range(1, 3):  # Apps 1-2
            count = self.db.query(XeroConnection).filter(
                and_(
                    XeroConnection.app_id == app_id,
                    XeroConnection.is_active == True
                )
            ).count()
            stats[app_id] = count
        return stats
    
    # Token History Operations
    def _log_token_history(self, connection: XeroConnection, access_token: str,
                          refresh_token: str, expires_at: datetime, scope: str,
                          refresh_type: str, old_token_hash: Optional[str] = None, new_token_hash: Optional[str] = None):
        """Log token history for audit trail"""
        # Create hashes for security (don't store actual tokens in history)
        access_token_hash = hashlib.sha256(access_token.encode()).hexdigest()
        refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        # Always set new_token_hash
        if not new_token_hash:
            new_token_hash = access_token_hash
        token_history = XeroTokenHistory(
            connection_id=connection.id,
            access_token_hash=access_token_hash,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            scope=scope,
            refresh_type=refresh_type,
            old_token_hash=old_token_hash,
            new_token_hash=new_token_hash
        )
        self.db.add(token_history)
        self.db.commit()
    
    def get_token_history(self, tenant_id: str, limit: int = 10) -> List[XeroTokenHistory]:
        """Get token history for a connection"""
        connection = self.get_connection(tenant_id)
        if not connection:
            return []
        
        return self.db.query(XeroTokenHistory).filter(
            XeroTokenHistory.connection_id == connection.id
        ).order_by(XeroTokenHistory.created_at.desc()).limit(limit).all()
    
    # API Logging Operations
    def log_api_call(self, connection_id: Optional[int], endpoint: str, method: str,
                    status_code: Optional[int] = None, response_time_ms: Optional[int] = None,
                    error_message: Optional[str] = None):
        """Log API call for monitoring and debugging"""
        api_log = XeroApiLog(
            connection_id=connection_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            response_time_ms=response_time_ms,
            error_message=error_message
        )
        
        self.db.add(api_log)
        self.db.commit()
    
    def get_api_logs(self, tenant_id: Optional[str] = None, limit: int = 50) -> List[XeroApiLog]:
        """Get API logs with optional filtering by tenant"""
        query = self.db.query(XeroApiLog)
        
        if tenant_id:
            connection = self.get_connection(tenant_id)
            if connection:
                query = query.filter(XeroApiLog.connection_id == connection.id)
        
        return query.order_by(XeroApiLog.created_at.desc()).limit(limit).all()
    
    # Utility Methods
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        total_connections = self.db.query(XeroConnection).filter(
            XeroConnection.is_active == True
        ).count()
        
        expired_connections = len(self.get_expired_connections())
        
        recent_logs = self.db.query(XeroApiLog).filter(
            XeroApiLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
        ).count()
        
        return {
            "total_connections": total_connections,
            "expired_connections": expired_connections,
            "recent_api_calls": recent_logs
        } 