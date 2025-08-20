from typing import Dict, Optional, List
from app.config import settings
import random
from collections import defaultdict


class XeroAppManager:
    """Manages multiple Xero app configurations and tenant distribution"""
    
    def __init__(self):
        self.app_configs = {
            1: {"client_id": settings.xero_app1_client_id, "client_secret": settings.xero_app1_client_secret},
            2: {"client_id": settings.xero_app2_client_id, "client_secret": settings.xero_app2_client_secret},
            3: {"client_id": settings.xero_app3_client_id, "client_secret": settings.xero_app3_client_secret},
        }
        
        # Validate app configurations during initialization
        for app_id, config in self.app_configs.items():
            if not config["client_id"] or not config["client_secret"]:
                print(f"Warning: App {app_id} credentials are empty or not configured")
                print(f"  client_id: {config['client_id']}")
                print(f"  client_secret: {'*' * len(config['client_secret']) if config['client_secret'] else 'None'}")
        
        self.tenant_mapping = settings.get_tenant_app_mapping()
        self.distribution_mode = settings.xero_app_distribution_mode
    
    def get_app_config(self, app_id: int) -> Dict[str, str]:
        """Get app configuration by app ID"""
        if app_id not in self.app_configs:
            raise ValueError(f"Invalid app_id: {app_id}. Available apps: {list(self.app_configs.keys())}")
        
        config = self.app_configs[app_id]
        
        # Validate that the config has the required fields
        if "client_id" not in config or "client_secret" not in config:
            raise ValueError(f"App {app_id} configuration missing required fields. Available fields: {list(config.keys())}")
        
        return config
    
    def get_app_id_for_tenant(self, tenant_id: str, existing_connections: Optional[List] = None) -> int:
        """Determine which app to use for a tenant"""
        # Check manual mapping first
        if tenant_id in self.tenant_mapping:
            return self.tenant_mapping[tenant_id]
        
        # Check if tenant already has a connection
        if existing_connections:
            for conn in existing_connections:
                if conn.tenant_id == tenant_id:
                    return conn.app_id
        
        # Use distribution strategy for new tenants
        if self.distribution_mode == "round_robin":
            return self._get_round_robin_app_id(existing_connections)
        elif self.distribution_mode == "load_balanced":
            return self._get_load_balanced_app_id(existing_connections)
        else:
            return 1  # Default to app 1
    
    def _get_round_robin_app_id(self, existing_connections: Optional[List] = None) -> int:
        """Distribute tenants using round-robin strategy"""
        if not existing_connections:
            return 1
        
        # Count connections per app
        app_counts = defaultdict(int)
        for conn in existing_connections:
            app_counts[conn.app_id] += 1
        
        # Find app with least connections
        min_count = min(app_counts.values()) if app_counts else 0
        available_apps = [app_id for app_id, count in app_counts.items() if count == min_count]
        
        if not available_apps:
            available_apps = list(self.app_configs.keys())
        
        return random.choice(available_apps)
    
    def _get_load_balanced_app_id(self, existing_connections: Optional[List] = None) -> int:
        """Distribute tenants using load balancing strategy"""
        if not existing_connections:
            return 1
        
        # Count active connections per app
        app_counts = defaultdict(int)
        for conn in existing_connections:
            if conn.is_active:
                app_counts[conn.app_id] += 1
        
        # Find app with least connections
        min_count = min(app_counts.values()) if app_counts else 0
        available_apps = [app_id for app_id, count in app_counts.items() if count == min_count]
        
        if not available_apps:
            available_apps = list(self.app_configs.keys())
        
        return random.choice(available_apps)
    
    def get_all_app_configs(self) -> Dict[int, Dict[str, str]]:
        """Get all app configurations"""
        return self.app_configs
    
    def validate_app_id(self, app_id: int) -> bool:
        """Validate if app_id exists"""
        return app_id in self.app_configs
    
    def get_app_stats(self, existing_connections: Optional[List] = None) -> Dict[int, int]:
        """Get connection count per app"""
        stats = {app_id: 0 for app_id in self.app_configs.keys()}
        
        if existing_connections:
            for conn in existing_connections:
                if conn.is_active:
                    stats[conn.app_id] += 1
        
        return stats 