from pydantic_settings import BaseSettings
from typing import Optional, List
import os
import json
from pathlib import Path


class Settings(BaseSettings):
    # Xero Multi-App OAuth2 Configuration
    xero_app1_client_id: str
    xero_app1_client_secret: str
    xero_app2_client_id: str
    xero_app2_client_secret: str
    xero_app3_client_id: str
    xero_app3_client_secret: str
    
    # App Distribution Settings
    xero_tenant_app_mapping: str = ""
    xero_app_distribution_mode: str = "round_robin"
    
    # Legacy support (for backward compatibility)
    xero_client_id: Optional[str] = None
    xero_client_secret: Optional[str] = None
    
    # Common Xero settings
    xero_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    xero_auth_url: str = "https://login.xero.com/identity/connect/authorize"
    xero_token_url: str = "https://identity.xero.com/connect/token"

    # finance.accountingactivity.read finance.bankstatementsplus.read finance.cashvalidation.read finance.statements.read scopes are valid. As xero doesn't exposed finance
    xero_scope: str = "offline_access accounting.settings accounting.settings.read accounting.transactions accounting.transactions.read accounting.budgets.read accounting.contacts accounting.contacts.read accounting.journals.read accounting.reports.read assets assets.read"
    
    # Application settings
    app_name: str = "Finance Assistant"
    debug: bool = False
    
    # CORS settings
    allowed_origins: List[str] = ["*"]  # Configure for production
    
    # API Security - will be loaded manually
    api_key_list: List[str] = []

    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_ssl: bool = False
    
    # Redis Cache Settings
    redis_cache_ttl: int = 3600  # 1 hour default TTL
    redis_report_cache_ttl: int = 86400  # 24 hours for report data
    
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
        
        # Load CORS origins from environment variable
        self._load_cors_origins()

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

    def _load_cors_origins(self):
        """Load CORS origins from environment variable"""
        cors_origins_env = os.getenv("ALLOWED_ORIGINS")
        if cors_origins_env:
            try:
                # Try to parse as JSON array
                self.allowed_origins = json.loads(cors_origins_env)
            except json.JSONDecodeError:
                # If not JSON, try comma-separated string
                self.allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
        
        # Fallback to wildcard if none provided (not recommended for production)
        if not self.allowed_origins or self.allowed_origins == ["*"]:
            if not self.debug:
                print("⚠️ Using wildcard CORS. Set ALLOWED_ORIGINS in .env for production use.")

    def get_xero_app_config(self, app_id: int) -> dict:
        """Get Xero app configuration by app ID"""
        app_configs = {
            1: {"client_id": self.xero_app1_client_id, "client_secret": self.xero_app1_client_secret},
            2: {"client_id": self.xero_app2_client_id, "client_secret": self.xero_app2_client_secret},
            3: {"client_id": self.xero_app3_client_id, "client_secret": self.xero_app3_client_secret},
        }
        return app_configs.get(app_id, app_configs[1])  # Default to app 1
    
    def get_tenant_app_mapping(self) -> dict:
        """Parse tenant to app mapping from environment"""
        mapping = {}
        if self.xero_tenant_app_mapping:
            for item in self.xero_tenant_app_mapping.split(','):
                if ':' in item:
                    tenant_id, app_id = item.strip().split(':', 1)
                    mapping[tenant_id.strip()] = int(app_id.strip())
        return mapping


settings = Settings() 