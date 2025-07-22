from pydantic_settings import BaseSettings
from typing import Optional, List
import os
import json
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
    
    # API Security - will be loaded manually
    api_key_list: List[str] = []
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from environment

    def __init__(self, **kwargs):
        # Try to load .env file manually first
        self._load_env_file()
        super().__init__(**kwargs)
        
        # Load API keys from environment variable
        self._load_api_keys()

    def _load_env_file(self):
        """Manually load .env file"""
        env_paths = [
            Path(".env"),  # Current directory
            Path(__file__).parent.parent / ".env",  # Two levels up from config.py
            Path.cwd() / ".env",  # Current working directory
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                os.environ[key.strip()] = value.strip()
                    return
                except Exception as e:
                    print(f"❌ Error loading .env file: {e}")
        
        print("❌ No .env file found in any of the expected locations")

    def _load_api_keys(self):
        """Load API keys from environment variable"""
        api_keys_env = os.getenv("API_KEYS")
        if api_keys_env:
            try:
                # Try to parse as JSON array
                self.api_key_list = json.loads(api_keys_env)
            except json.JSONDecodeError:
                # If not JSON, try comma-separated string
                self.api_key_list = [key.strip() for key in api_keys_env.split(",") if key.strip()]
        
        # Fallback to default keys if none provided
        if not self.api_key_list:
            self.api_key_list = [
                "default-api-key-for-development",  # Replace with your actual keys
            ]
            print("⚠️ Using default API key. Set API_KEYS in .env for production use.")


settings = Settings() 