from pydantic_settings import BaseSettings
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    # Xero OAuth2 Configuration
    xero_client_id: str
    xero_client_secret: str
    xero_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    
    # Xero API URLs
    xero_auth_url: str = "https://login.xero.com/identity/connect/authorize"
    xero_token_url: str = "https://identity.xero.com/connect/token"
    xero_scope: str = "offline_access accounting.transactions accounting.contacts"
    
    # Application settings
    app_name: str = "Finance Assistant"
    debug: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        # Try to load .env file manually first
        self._load_env_file()
        super().__init__(**kwargs)
        # Debug: Print environment variables
        print(f"🔍 Environment check:")
        print(f"   XERO_CLIENT_ID from env: {os.getenv('XERO_CLIENT_ID', 'NOT_FOUND')}")
        print(f"   XERO_CLIENT_SECRET from env: {os.getenv('XERO_CLIENT_SECRET', 'NOT_FOUND')}")
        print(f"   .env file path: {os.path.abspath('.env')}")
        print(f"   Current working directory: {os.getcwd()}")
        print(f"   Settings loaded - client_id: {self.xero_client_id[:10] if self.xero_client_id else 'NOT_SET'}...")

    def _load_env_file(self):
        """Manually load .env file"""
        env_paths = [
            Path(".env"),  # Current directory
            Path(__file__).parent.parent / ".env",  # Two levels up from config.py
            Path.cwd() / ".env",  # Current working directory
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                print(f"📁 Found .env file at: {env_path.absolute()}")
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                os.environ[key.strip()] = value.strip()
                    print(f"✅ Loaded .env file from: {env_path}")
                    return
                except Exception as e:
                    print(f"❌ Error loading .env file: {e}")
        
        print("❌ No .env file found in any of the expected locations")


settings = Settings() 