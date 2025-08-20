from fastapi import APIRouter, HTTPException, Depends, Query, Request, Path
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime, timezone

from app.services.xero_auth import XeroAuthService
from app.services.xero_app_manager import XeroAppManager
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
    app_id: int = Query(1, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Generate authorization URL and redirect to Xero login for specific app
    
    This endpoint:
    1. Generates a secure state parameter
    2. Creates PKCE code verifier/challenge (if enabled)
    3. Builds the authorization URL for the specified app
    4. Returns the authorization URL
    """
    try:
        auth_url, auth_state = xero_service.generate_auth_url(app_id=app_id, use_pkce=use_pkce)
        
        return {
            "authorization_url": auth_url,
            "state": auth_state.state,
            "app_id": app_id,
            "message": "Redirect to this URL to authenticate with Xero"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/login/{app_id}")
async def login_with_app(
    app_id: int = Path(..., ge=1, le=3, description="Xero app ID (1-3)"),
    use_pkce: bool = Query(True, description="Use PKCE for enhanced security"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Generate authorization URL for specific Xero app
    
    This endpoint:
    1. Generates a secure state parameter
    2. Creates PKCE code verifier/challenge (if enabled)
    3. Builds the authorization URL for the specified app
    4. Returns the authorization URL
    """
    try:
        auth_url, auth_state = xero_service.generate_auth_url(app_id=app_id, use_pkce=use_pkce)
        
        return {
            "authorization_url": auth_url,
            "state": auth_state.state,
            "app_id": app_id,
            "message": "Redirect to this URL to authenticate with Xero"
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/login/redirect")
async def login_redirect(
    use_pkce: bool = Query(True, description="Use PKCE for enhanced security"),
    app_id: int = Query(1, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Redirect directly to Xero login page for specific app
    
    This is a convenience endpoint that immediately redirects to Xero
    """
    try:
        auth_url, auth_state = xero_service.generate_auth_url(app_id=app_id, use_pkce=use_pkce)
        return RedirectResponse(url=auth_url)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")



@router.post("/refresh/{tenant_id}")
async def refresh_token(
    tenant_id: str,
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Refresh access token for a specific tenant
    
    This endpoint:
    1. Gets the stored connection for the tenant
    2. Checks if token needs refresh
    3. Refreshes the token if needed
    4. Updates the stored connection in database
    """
    try:
        # Get existing connection
        connection = xero_service.get_connection(tenant_id, app_id)
        if not connection:
            raise HTTPException(status_code=404, detail=f"Connection not found for tenant {tenant_id}, app_id {app_id}")
        
        print(f"Found connection: {connection.tenant_name} (ID: {connection.tenant_id}, App: {connection.app_id})")
        print(f"Token expires at: {connection.expires_at}")
        print(f"Current time: {datetime.utcnow()}")
        
        # Check if token needs refresh
        buffer_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        buffer_time = buffer_time.replace(minute=buffer_time.minute + 5)
        
        if buffer_time < connection.expires_at:
            return {
                "message": "Token is still valid",
                "expires_at": connection.expires_at.isoformat()
            }
        
        print(f"Token needs refresh. Buffer time: {buffer_time}, Expires: {connection.expires_at}")
        
        # Refresh token
        token_response = await xero_service.refresh_access_token(
            connection.refresh_token, 
            connection.app_id,
            tenant_id=tenant_id
        )
        
        # Update connection
        updated_connection = xero_service.update_connection_tokens(tenant_id, token_response, connection.app_id)
        
        return {
            "message": "Token refreshed successfully",
            "tenant": {
                "id": updated_connection.tenant_id,
                "name": updated_connection.tenant_name,
                "app_id": updated_connection.app_id
            },
            "token_info": {
                "expires_at": token_response.expires_at.isoformat(),
                "scope": token_response.scope
            }
        }
    
    except Exception as e:
        import traceback
        error_details = str(e)
        if not error_details or error_details == "Token refresh failed: ":
            error_details = f"Unknown error occurred: {type(e).__name__}"
        
        # Check if this is an invalid_grant error
        if "invalid_grant" in error_details.lower():
            # Handle invalid grant error
            error_info = xero_service.handle_invalid_grant_error(
                tenant_id, 
                app_id or 1, 
                error_details
            )
            raise HTTPException(
                status_code=401, 
                detail={
                    "error": "invalid_grant",
                    "message": "The connection has expired and needs to be re-authenticated",
                    "requires_re_authentication": True,
                    "re_auth_url": error_info.get("re_auth_url"),
                    "tenant_id": tenant_id,
                    "app_id": app_id or 1
                }
            )
        
        # Log the full error for debugging
        print(f"Token refresh error for tenant {tenant_id}, app_id {app_id}: {error_details}")
        print(f"Full traceback: {traceback.format_exc()}")
        
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {error_details}")


@router.get("/connections")
async def list_connections(
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Filter by app ID"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """List all Xero connections"""
    try:
        connections = xero_service.get_connections_by_app(app_id) if app_id else xero_service.get_all_connections()
        
        return {
            "connections": [
                {
                    "id": conn.id,
                    "tenant_id": conn.tenant_id,
                    "tenant_name": conn.tenant_name,
                    "ownership": conn.ownership,
                    "business_type": conn.business_type,
                    "app_id": conn.app_id,
                    # "expires_at": conn.expires_at.isoformat(),
                    # "is_active": conn.is_active,
                    # "created_at": conn.created_at.isoformat(),
                    # "updated_at": conn.updated_at.isoformat()
                }
                for conn in connections
            ],
            "total": len(connections)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list connections: {str(e)}")


@router.get("/connections/{tenant_id}")
async def get_connection(
    tenant_id: str,
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Get connection details for a specific tenant"""
    try:
        connection = xero_service.get_connection(tenant_id, app_id)
        if not connection:
            raise HTTPException(status_code=404, detail=f"Connection not found for tenant {tenant_id}")
        
        return {
            "id": connection.id,
            "tenant_id": connection.tenant_id,
            "tenant_name": connection.tenant_name,
            "app_id": connection.app_id,
            "expires_at": connection.expires_at.isoformat(),
            "is_active": connection.is_active,
            "created_at": connection.created_at.isoformat(),
            "updated_at": connection.updated_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get connection: {str(e)}")


@router.delete("/connections/{tenant_id}")
async def delete_connection(
    tenant_id: str,
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Delete a connection for a specific tenant"""
    try:
        success = xero_service.delete_connection(tenant_id, app_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Connection not found for tenant {tenant_id}")
        
        return {"message": f"Connection for tenant {tenant_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete connection: {str(e)}")


@router.post("/connections/{tenant_id}/deactivate")
async def deactivate_connection(
    tenant_id: str,
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Deactivate a connection for a specific tenant"""
    try:
        success = xero_service.deactivate_connection(tenant_id, app_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Connection not found for tenant {tenant_id}")
        
        return {"message": f"Connection for tenant {tenant_id} deactivated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate connection: {str(e)}")


@router.post("/connections/{tenant_id}/handle-invalid-grant")
async def handle_invalid_grant(
    tenant_id: str,
    app_id: int = Query(1, ge=1, le=3, description="Xero app ID (1-3)"),
    error_message: str = Query("Invalid grant error", description="Error message from the failed request"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Handle invalid_grant errors for a specific tenant
    
    This endpoint:
    1. Deactivates the problematic connection
    2. Logs the error
    3. Returns re-authentication information
    """
    try:
        error_info = xero_service.handle_invalid_grant_error(tenant_id, app_id, error_message)
        
        return {
            "message": "Connection deactivated due to invalid grant error",
            "requires_re_authentication": True,
            "re_auth_url": error_info.get("re_auth_url"),
            "tenant_id": tenant_id,
            "app_id": app_id,
            "tenant_name": error_info.get("tenant_name", "Unknown")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to handle invalid grant error: {str(e)}")


@router.get("/connections/{tenant_id}/history")
async def get_token_history(
    tenant_id: str,
    limit: int = Query(10, description="Number of history records to return"),
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Xero app ID (1-3)"),
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


@router.get("/app-stats")
async def get_app_stats(
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Get connection statistics per app"""
    connections = xero_service.get_all_connections()
    app_manager = XeroAppManager()
    stats = app_manager.get_app_stats(connections)
    
    return {
        "app_stats": stats,
        "total_connections": sum(stats.values()),
        "distribution_mode": app_manager.distribution_mode
    }


@router.post("/cleanup")
async def cleanup_expired_states(
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """Clean up expired auth states from database"""
    deleted_count = xero_service.cleanup_expired_states()
    return {"message": f"Cleaned up {deleted_count} expired states"} 


@router.get("/auth/scope/{tenant_id}")
async def get_connection_scope(
    tenant_id: str,
    app_id: Optional[int] = Query(None, ge=1, le=3, description="Xero app ID (1-3)"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Get the current scope for a connection.
    """
    try:
        # Get the existing connection
        connection = xero_service.get_connection(tenant_id, app_id)
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        return {
            "tenant": {
                "id": connection.tenant_id,
                "name": connection.tenant_name,
                "app_id": connection.app_id,
                "scope": connection.scope,
                "expires_at": connection.expires_at.isoformat() if connection.expires_at else None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scope: {str(e)}") 