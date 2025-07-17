from fastapi import Header, HTTPException, status
from app.config import settings

def api_key_auth(x_api_key: str = Header(...)):
    if x_api_key not in settings.api_key_list:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        ) 