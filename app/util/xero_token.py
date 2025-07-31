from app.models.xero_auth import XeroTokenResponse
from datetime import datetime, timezone

def register_xero_token_handlers(api_client, token_dict, tenant_id, xero_service, app_id=None):
    """
    Register token getter and saver for the Xero SDK client.
    - api_client: The Xero ApiClient instance
    - token_dict: The current token dictionary
    - tenant_id: The Xero tenant ID
    - xero_service: The XeroAuthService instance for persistence
    - app_id: The Xero app ID for multi-app support
    """
    @api_client.oauth2_token_getter
    def obtain_xero_oauth2_token():
        return token_dict

    @api_client.oauth2_token_saver
    def store_xero_oauth2_token(new_token):
        if new_token.get("access_token") != token_dict["access_token"]:
            expires_at = new_token.get("expires_at")
            if expires_at and isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            # Calculate expires_in from expires_at if available
            expires_in = None
            if expires_at:
                if isinstance(expires_at, float):
                    # expires_at is a timestamp, convert to datetime
                    expires_at_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                    expires_in = int((expires_at_dt - datetime.now(timezone.utc)).total_seconds())
                else:
                    # expires_at is already a datetime
                    expires_in = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            
            # Convert scope list to string if needed
            scope = new_token.get("scope", token_dict["scope"])
            if isinstance(scope, list):
                scope = " ".join(scope)
            
            # Ensure expires_at is a datetime object
            final_expires_at = None
            if expires_at:
                if isinstance(expires_at, float):
                    final_expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                elif isinstance(expires_at, datetime):
                    final_expires_at = expires_at
            
            token_response = XeroTokenResponse(
                access_token=new_token["access_token"],
                refresh_token=new_token.get("refresh_token", token_dict["refresh_token"]),
                expires_in=expires_in or 1800,  # Default to 30 minutes if not available
                token_type=new_token.get("token_type", "Bearer"),
                scope=scope,
                id_token=new_token.get("id_token"),
                expires_at=final_expires_at,
            )
            xero_service.update_connection_tokens(tenant_id, token_response, app_id)