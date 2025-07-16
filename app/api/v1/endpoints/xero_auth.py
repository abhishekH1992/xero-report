from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime

from app.services.xero_auth import XeroAuthService
# from app.models.xero_auth import XeroTokenResponse, XeroConnection
from app.database.database import get_db
from app.database.repository import XeroAuthRepository

router = APIRouter(prefix="/auth", tags=["Xero Authentication"])


def get_xero_auth_service(db: Session = Depends(get_db)) -> XeroAuthService:
    """Dependency to get XeroAuthService with database repository"""
    repo = XeroAuthRepository(db)
    return XeroAuthService(repo)


@router.get("/login")
async def login(
    use_pkce: bool = Query(True, description="Use PKCE for enhanced security"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Generate authorization URL and redirect to Xero login
    
    This endpoint:
    1. Generates a secure state parameter
    2. Creates PKCE code verifier/challenge (if enabled)
    3. Builds the authorization URL
    4. Redirects user to Xero for authentication
    """
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
    """
    Redirect directly to Xero login page
    
    This is a convenience endpoint that immediately redirects to Xero
    """
    try:
        auth_url, auth_state = xero_service.generate_auth_url(use_pkce=use_pkce)
        return RedirectResponse(url=auth_url)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/callback")
async def auth_callback(
    code: str = Query(..., description="Authorization code from Xero"),
    state: str = Query(..., description="State parameter for verification"),
    error: Optional[str] = Query(None, description="Error from Xero if any"),
    error_description: Optional[str] = Query(None, description="Error description from Xero"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Handle OAuth2 callback from Xero
    
    This endpoint:
    1. Validates the state parameter
    2. Exchanges authorization code for tokens
    3. Gets tenant information
    4. Saves connection data to database
    5. Returns success response or error
    
    Note: Authorization codes can only be used once and expire quickly (usually 10 minutes)
    """
    # Check for OAuth2 errors
    if error:
        error_msg = f"OAuth2 error: {error}"
        if error_description:
            error_msg += f" - {error_description}"
        raise HTTPException(status_code=400, detail=error_msg)
    
    try:
        # Exchange code for tokens
        token_response = await xero_service.exchange_code_for_tokens(code, state)
        
        # Get tenant information
        tenant_info = await xero_service.get_tenant_info(token_response.access_token)
        
        # Save connection
        if tenant_info:
            # Log all available tenants for debugging
            print(f"Available tenants: {[t.get('tenantName', 'Unknown') for t in tenant_info]}")
            
            # Try to find the most recently authenticated tenant
            # Xero usually returns the active/selected tenant first
            tenant = tenant_info[0]  # Start with first tenant
            
            # If there are multiple tenants, look for one that's not already in our database
            if len(tenant_info) > 1:
                existing_connections = xero_service.get_all_connections()
                existing_tenant_ids = {conn.tenant_id for conn in existing_connections}
                
                # Try to find a tenant that's not already connected
                for t in tenant_info:
                    if t.get('tenantId') not in existing_tenant_ids:
                        tenant = t
                        print(f"Selected new tenant: {tenant.get('tenantName')}")
                        break
                else:
                    # If all tenants are already connected, use the first one
                    print(f"All tenants already connected, using first: {tenant.get('tenantName')}")
            
            connection = xero_service.save_connection(
                tenant_id=tenant['tenantId'],
                tenant_name=tenant['tenantName'],
                token_response=token_response
            )
            
            return {
                "success": True,
                "message": "Successfully authenticated with Xero",
                "tenant": {
                    "id": connection.tenant_id,
                    "name": connection.tenant_name
                },
                "token_info": {
                    "expires_at": token_response.expires_at.isoformat(),
                    "scope": token_response.scope
                }
            }
        else:
            raise HTTPException(status_code=400, detail="No tenant information found")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/callback/html")
async def auth_callback_html(
    code: str = Query(..., description="Authorization code from Xero"),
    state: str = Query(..., description="State parameter for verification"),
    error: Optional[str] = Query(None, description="Error from Xero if any"),
    error_description: Optional[str] = Query(None, description="Error description from Xero"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Handle OAuth2 callback with HTML response for better user experience
    """
    if error:
        error_msg = f"OAuth2 error: {error}"
        if error_description:
            error_msg += f" - {error_description}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <h1 class="error">Authentication Failed</h1>
            <p>{error_msg}</p>
            <p><a href="/api/v1/auth/login">Try Again</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=400)
    
    try:
        # Exchange code for tokens
        token_response = await xero_service.exchange_code_for_tokens(code, state)
        
        # Get tenant information
        tenant_info = await xero_service.get_tenant_info(token_response.access_token)
        
        # Save connection
        if tenant_info:
            # Log all available tenants for debugging
            print(f"Available tenants: {[t.get('tenantName', 'Unknown') for t in tenant_info]}")
            
            # Try to find the most recently authenticated tenant
            # Xero usually returns the active/selected tenant first
            tenant = tenant_info[0]  # Start with first tenant
            
            # If there are multiple tenants, look for one that's not already in our database
            if len(tenant_info) > 1:
                existing_connections = xero_service.get_all_connections()
                existing_tenant_ids = {conn.tenant_id for conn in existing_connections}
                
                # Try to find a tenant that's not already connected
                for t in tenant_info:
                    if t.get('tenantId') not in existing_tenant_ids:
                        tenant = t
                        print(f"Selected new tenant: {tenant.get('tenantName')}")
                        break
                else:
                    # If all tenants are already connected, use the first one
                    print(f"All tenants already connected, using first: {tenant.get('tenantName')}")
            
            connection = xero_service.save_connection(
                tenant_id=tenant['tenantId'],
                tenant_name=tenant['tenantName'],
                token_response=token_response
            )
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }}
                    .success {{ color: green; }}
                    .info {{ background: #f0f0f0; padding: 20px; margin: 20px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <h1 class="success">✅ Authentication Successful!</h1>
                <div class="info">
                    <h2>Connected to Xero</h2>
                    <p><strong>Organization:</strong> {connection.tenant_name}</p>
                    <p><strong>Tenant ID:</strong> {connection.tenant_id}</p>
                    <p><strong>Token Expires:</strong> {token_response.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                    <p><strong>Scopes:</strong> {token_response.scope}</p>
                </div>
                <p>You can now close this window and return to your application.</p>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        else:
            raise HTTPException(status_code=400, detail="No tenant information found")
    
    except ValueError as e:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <h1 class="error">Authentication Failed</h1>
            <p>{str(e)}</p>
            <p><a href="/api/v1/auth/login">Try Again</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=400)
    
    except Exception as e:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <h1 class="error">Authentication Failed</h1>
            <p>An unexpected error occurred: {str(e)}</p>
            <p><a href="/api/v1/auth/login">Try Again</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=500)


@router.post("/refresh/{tenant_id}")
async def refresh_token(
    tenant_id: str,
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
        connection = xero_service.get_connection(tenant_id)
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        # Check if token needs refresh
        buffer_time = datetime.utcnow().replace(second=0, microsecond=0)
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