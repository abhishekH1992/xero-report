from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime

from app.services.xero_auth import XeroAuthService
from app.util.auth import api_key_auth
# from app.models.xero_auth import XeroTokenResponse, XeroConnection

router = APIRouter(
    prefix="/auth",
    tags=["Xero Authentication"],
    dependencies=[Depends(api_key_auth)]
)

get_xero_auth_service = XeroAuthService.get_service_dependency()


@router.get("/login")
async def login(
    use_pkce: bool = Query(True, description="Use PKCE for enhanced security"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Generate authorization URL and redirect to Xero login"""
    
    try:
        auth_url, auth_state = xero_service.generate_auth_url(use_pkce=use_pkce)
        
        return {
            "authorization_url": auth_url,
            "state": auth_state.state,
            "message": "Redirect to this URL to authenticate with Xero"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/login/redirect")
async def login_redirect(
    use_pkce: bool = Query(True, description="Use PKCE for enhanced security"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Redirect directly to Xero login page"""
    
    try:
        auth_url, auth_state = xero_service.generate_auth_url(use_pkce=use_pkce)
        return RedirectResponse(url=auth_url)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.post("/refresh/{tenant_id}")
async def refresh_token(
    tenant_id: str,
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Refresh access token for a specific tenant"""
    
    try:
        # Get existing connection
        connection = xero_service.get_connection(tenant_id)
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        # Check if token needs refresh
        buffer_time = datetime.utcnow().replace(second=0, minute=0)
        buffer_time = buffer_time.replace(minute=buffer_time.minute + 5)
        
        if buffer_time < connection.expires_at:
            return {
                "message": "Token is still valid",
                "expires_at": connection.expires_at.isoformat()
            }
        
        # Refresh token
        token_response = await xero_service.refresh_access_token(
            connection.refresh_token, 
            tenant_id=tenant_id
        )
        
        # Update connection
        updated_connection = xero_service.update_connection_tokens(tenant_id, token_response)
        
        return {
            "message": "Token refreshed successfully",
            "tenant": {
                "id": updated_connection.tenant_id,
                "name": updated_connection.tenant_name
            },
            "token_info": {
                "expires_at": token_response.expires_at.isoformat(),
                "scope": token_response.scope
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")


@router.get("/connections")
async def list_connections(
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """List all stored Xero connections from database"""
    connections = xero_service.get_all_connections()
    
    connection_list = []
    for connection in connections:
        connection_list.append({
            "tenant_id": connection.tenant_id,
            "tenant_name": connection.tenant_name,
            "expires_at": connection.expires_at.isoformat(),
            "needs_refresh": connection.expires_at <= datetime.utcnow(),
            "created_at": connection.created_at.isoformat(),
            "updated_at": connection.updated_at.isoformat(),
            "is_active": connection.is_active
        })
    
    return {
        "connections": connection_list,
        "count": len(connection_list)
    }


@router.get("/connections/{tenant_id}")
async def get_connection(
    tenant_id: str,
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Get specific connection details from database"""
    connection = xero_service.get_connection(tenant_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")    
    return {
        "tenant_id": connection.tenant_id,
        "tenant_name": connection.tenant_name,
        "expires_at": connection.expires_at.isoformat(),
        "needs_refresh": connection.expires_at <= datetime.utcnow(),
        "scope": connection.scope,
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
        "is_active": connection.is_active
    }


@router.delete("/connections/{tenant_id}")
async def delete_connection(
    tenant_id: str,
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Delete a stored connection from database"""
    success = xero_service.delete_connection(tenant_id)
    if success:
        return {"message": "Connection deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Connection not found")


@router.post("/connections/{tenant_id}/deactivate")
async def deactivate_connection(
    tenant_id: str,
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Deactivate a connection (soft delete)"""
    success = xero_service.deactivate_connection(tenant_id)
    if success:
        return {"message": "Connection deactivated successfully"}
    else:
        raise HTTPException(status_code=404, detail="Connection not found")


@router.get("/connections/{tenant_id}/history")
async def get_token_history(
    tenant_id: str,
    limit: int = Query(10, description="Number of history records to return"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Get token refresh history for a connection"""
    history = xero_service.get_token_history(tenant_id, limit)
    
    history_list = []
    for record in history:
        history_list.append({
            "refresh_type": record.refresh_type,
            "expires_at": record.expires_at.isoformat(),
            "scope": record.scope,
            "created_at": record.created_at.isoformat()
        })
    
    return {
        "tenant_id": tenant_id,
        "history": history_list,
        "count": len(history_list)
    }


@router.get("/logs")
async def get_api_logs(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    limit: int = Query(50, description="Number of log records to return"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Get API call logs with optional filtering"""
    logs = xero_service.get_api_logs(tenant_id, limit)
    
    log_list = []
    for log in logs:
        log_list.append({
            "endpoint": log.endpoint,
            "method": log.method,
            "status_code": log.status_code,
            "response_time_ms": log.response_time_ms,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat()
        })
    
    return {
        "logs": log_list,
        "count": len(log_list),
        "filtered_by_tenant": tenant_id is not None
    }


@router.get("/stats")
async def get_connection_stats(
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Get connection and API statistics"""
    return xero_service.get_connection_stats()


@router.post("/cleanup")
async def cleanup_expired_states(
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Clean up expired auth states from database"""
    deleted_count = xero_service.cleanup_expired_states()
    return {"message": f"Cleaned up {deleted_count} expired states"} 