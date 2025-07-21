from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse
from typing import Optional
from app.services.xero_auth import XeroAuthService

router = APIRouter(
    tags=["Xero Authentication Callback"]
)

get_xero_auth_service = XeroAuthService.get_service_dependency()

@router.get("/auth/callback")
async def auth_callback(
    code: str = Query(..., description="Authorization code from Xero"),
    state: str = Query(..., description="State parameter for verification"),
    error: Optional[str] = Query(None, description="Error from Xero if any"),
    error_description: Optional[str] = Query(None, description="Error description from Xero"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    if error:
        error_msg = f"OAuth2 error: {error}"
        if error_description:
            error_msg += f" - {error_description}"
        raise HTTPException(status_code=400, detail=error_msg)
    try:
        token_response = await xero_service.exchange_code_for_tokens(code, state)
        tenant_info = await xero_service.get_tenant_info(token_response.access_token)
        if tenant_info:
            print(f"Available tenants: {[t.get('tenantName', 'Unknown') for t in tenant_info]}")
            tenant = tenant_info[0]
            
            if len(tenant_info) > 1:
                existing_connections = xero_service.get_all_connections()
                existing_tenant_ids = {conn.tenant_id for conn in existing_connections}
                for t in tenant_info:
                    if t.get('tenantId') not in existing_tenant_ids:
                        tenant = t
                        print(f"Selected new tenant: {tenant.get('tenantName')}")
                        break
                else:
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

@router.get("/auth/callback/html")
async def auth_callback_html(
    code: str = Query(..., description="Authorization code from Xero"),
    state: str = Query(..., description="State parameter for verification"),
    error: Optional[str] = Query(None, description="Error from Xero if any"),
    error_description: Optional[str] = Query(None, description="Error description from Xero"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
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
        token_response = await xero_service.exchange_code_for_tokens(code, state)
        tenant_info = await xero_service.get_tenant_info(token_response.access_token)
        if tenant_info:
            print(f"Available tenants: {[t.get('tenantName', 'Unknown') for t in tenant_info]}")
            tenant = tenant_info[0]
            if len(tenant_info) > 1:
                existing_connections = xero_service.get_all_connections()
                existing_tenant_ids = {conn.tenant_id for conn in existing_connections}
                for t in tenant_info:
                    if t.get('tenantId') not in existing_tenant_ids:
                        tenant = t
                        print(f"Selected new tenant: {tenant.get('tenantName')}")
                        break
                else:
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