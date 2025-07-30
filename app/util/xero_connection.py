from xero_python.accounting import AccountingApi
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from datetime import datetime, timezone

from app.util.xero_token import register_xero_token_handlers
from app.services.xero_auth import XeroAuthService
from app.database.models import XeroConnection


def create_xero_api_client(connection: XeroConnection, tenant_id: str, xero_service: XeroAuthService) -> AccountingApi:
    """
    Create a configured Xero API client with automatic token refresh.
    
    Args:
        connection: The Xero connection from database
        tenant_id: The Xero tenant ID
        xero_service: The XeroAuthService instance for persistence
        
    Returns:
        AccountingApi: Configured API client ready to use
    """
    # Get app-specific credentials using the auth service (with proper error handling)
    try:
        client_id, client_secret = xero_service.get_app_credentials(connection.app_id)
    except Exception as e:
        raise ValueError(f"Failed to get credentials for app {connection.app_id}: {e}")
    
    # Build Xero SDK client with app-specific credentials
    api_client = ApiClient(
        Configuration(
            debug=False,
            oauth2_token=OAuth2Token(
                client_id=client_id,
                client_secret=client_secret
            ),
        ),
        pool_threads=1,
    )

    # Prepare token dictionary for the SDK
    token_dict = {
        "access_token": connection.access_token,
        "refresh_token": connection.refresh_token,
        "scope": connection.scope.split(),
        "expires_at": connection.expires_at.timestamp(),
        "expires_in": int((connection.expires_at - datetime.now(timezone.utc)).total_seconds()),
        "token_type": "Bearer"
    }

    # Register handlers for automatic refresh first, then set the token
    register_xero_token_handlers(api_client, token_dict, tenant_id, xero_service, connection.app_id)
    api_client.set_oauth2_token(token_dict)

    # Create and return Accounting API instance
    return AccountingApi(api_client) 