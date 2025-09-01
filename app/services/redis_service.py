import redis
import json
import pickle
import ssl
import certifi
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
import hashlib
from app.config import settings


class RedisService:
    """Generic Redis service for caching and data storage"""
    
    def __init__(self):
        # Prefer a full rediss:// URL via secrets
        url = settings.redis_url
        if not url or url == "redis://localhost:6379":
            # fallback, still using TLS when talking to Upstash
            if settings.redis_password:
                url = (
                    f"rediss://default:{settings.redis_password}"
                    f"@{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
                )
            else:
                # Local development fallback
                url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"

        # Determine if this is a local or remote connection
        is_local = (
            'localhost' in url or 
            '127.0.0.1' in url or 
            (settings.redis_host in ['localhost', '127.0.0.1'] and not settings.redis_password)
        )
        
        if is_local:
            # Local Redis - no SSL needed
            self.redis_client = redis.from_url(
                url,
                decode_responses=False,                 # keep bytes for pickle
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=10,                     # connection pool limit
            )
        else:
            # Remote Redis (Upstash) - use SSL
            self.redis_client = redis.from_url(
                url,
                decode_responses=False,                 # keep bytes for pickle
                ssl_cert_reqs=ssl.CERT_REQUIRED,        # verify server certs
                ssl_ca_certs=certifi.where(),           # CA bundle
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=10,                     # connection pool limit
            )

        self.default_ttl = settings.redis_cache_ttl
    
    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate a consistent cache key from parameters"""
        if not kwargs:
            return prefix
        
        # Sort kwargs to ensure consistent key generation
        sorted_items = sorted(kwargs.items())
        key_string = f"{prefix}:{':'.join(f'{k}={v}' for k, v in sorted_items)}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _serialize_data(self, data: Any) -> bytes:
        """Serialize data for Redis storage"""
        try:
            return pickle.dumps(data)
        except Exception:
            # Fallback to JSON for simple data types
            return json.dumps(data, default=str).encode()
    
    def _deserialize_data(self, data: bytes) -> Any:
        """Deserialize data from Redis storage"""
        try:
            return pickle.loads(data)
        except Exception:
            # Fallback to JSON
            return json.loads(data.decode())
    
    # Basic CRUD Operations
    
    def set_cache(
        self,
        key_prefix: str,
        data: Any,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Set data in cache
        
        Args:
            key_prefix: Prefix for the cache key
            data: Data to cache
            ttl: Time to live in seconds (default: from settings)
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(key_prefix, **kwargs)
        
        try:
            serialized_data = self._serialize_data(data)
            return self.redis_client.setex(
                cache_key,
                ttl or self.default_ttl,
                serialized_data
            )
        except Exception as e:
            print(f"Error setting cache for key {cache_key}: {e}")
            return False
    
    def get_cache(
        self,
        key_prefix: str,
        **kwargs
    ) -> Optional[Any]:
        """
        Get data from cache
        
        Args:
            key_prefix: Prefix for the cache key
            **kwargs: Additional parameters for key generation
            
        Returns:
            Cached data or None if not found
        """
        cache_key = self._generate_cache_key(key_prefix, **kwargs)
        
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return self._deserialize_data(cached_data)
            return None
        except Exception as e:
            print(f"Error getting cache for key {cache_key}: {e}")
            return None
    
    def delete_cache(
        self,
        key_prefix: str,
        **kwargs
    ) -> bool:
        """
        Delete data from cache
        
        Args:
            key_prefix: Prefix for the cache key
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(key_prefix, **kwargs)
        
        try:
            return bool(self.redis_client.delete(cache_key))
        except Exception as e:
            print(f"Error deleting cache for key {cache_key}: {e}")
            return False
    
    def exists_cache(
        self,
        key_prefix: str,
        **kwargs
    ) -> bool:
        """
        Check if cache key exists
        
        Args:
            key_prefix: Prefix for the cache key
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if key exists, False otherwise
        """
        cache_key = self._generate_cache_key(key_prefix, **kwargs)
        
        try:
            return bool(self.redis_client.exists(cache_key))
        except Exception as e:
            print(f"Error checking cache existence for key {cache_key}: {e}")
            return False
    
    # Advanced Operations
    
    def set_cache_with_metadata(
        self,
        key_prefix: str,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Set data in cache with additional metadata
        
        Args:
            key_prefix: Prefix for the cache key
            data: Data to cache
            metadata: Additional metadata (created_at, user_id, etc.)
            ttl: Time to live in seconds
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if successful, False otherwise
        """
        cache_data = {
            "data": data,
            "metadata": metadata or {},
            "cached_at": datetime.utcnow().isoformat(),
            "ttl": ttl or self.default_ttl
        }
        
        return self.set_cache(key_prefix, cache_data, ttl, **kwargs)
    
    def get_cache_with_metadata(
        self,
        key_prefix: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get data from cache with metadata
        
        Args:
            key_prefix: Prefix for the cache key
            **kwargs: Additional parameters for key generation
            
        Returns:
            Dict with 'data' and 'metadata' keys, or None if not found
        """
        return self.get_cache(key_prefix, **kwargs)
    
    def get_cache_data_only(
        self,
        key_prefix: str,
        **kwargs
    ) -> Optional[Any]:
        """
        Get only the data from cache (without metadata)
        
        Args:
            key_prefix: Prefix for the cache key
            **kwargs: Additional parameters for key generation
            
        Returns:
            Cached data or None if not found
        """
        cached_item = self.get_cache(key_prefix, **kwargs)
        if cached_item and isinstance(cached_item, dict):
            return cached_item.get("data")
        return cached_item
    
    # Pattern Operations
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching a pattern
        
        Args:
            pattern: Redis pattern (e.g., "cache:*", "user:*:profile")
            
        Returns:
            Number of keys deleted
        """
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            print(f"Error clearing pattern {pattern}: {e}")
            return 0
    
    def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """
        Get all keys matching a pattern
        
        Args:
            pattern: Redis pattern
            
        Returns:
            List of matching keys
        """
        try:
            keys = self.redis_client.keys(pattern)
            return [key.decode() if isinstance(key, bytes) else key for key in keys]
        except Exception as e:
            print(f"Error getting keys for pattern {pattern}: {e}")
            return []
    
    def get_cache_size(self, pattern: str = "*") -> int:
        """
        Get number of keys matching a pattern
        
        Args:
            pattern: Redis pattern (default: all keys)
            
        Returns:
            Number of matching keys
        """
        try:
            keys = self.redis_client.keys(pattern)
            return len(keys)
        except Exception as e:
            print(f"Error getting cache size for pattern {pattern}: {e}")
            return 0
    
    # TTL Operations
    
    def get_ttl(self, key_prefix: str, **kwargs) -> Optional[int]:
        """
        Get remaining TTL for a cache key
        
        Args:
            key_prefix: Prefix for the cache key
            **kwargs: Additional parameters for key generation
            
        Returns:
            Remaining TTL in seconds, -1 if no expiry, None if key doesn't exist
        """
        cache_key = self._generate_cache_key(key_prefix, **kwargs)
        
        try:
            ttl = self.redis_client.ttl(cache_key)
            return ttl if ttl != -2 else None  # -2 means key doesn't exist
        except Exception as e:
            print(f"Error getting TTL for key {cache_key}: {e}")
            return None
    
    def extend_ttl(
        self,
        key_prefix: str,
        new_ttl: int,
        **kwargs
    ) -> bool:
        """
        Extend TTL for a cache key
        
        Args:
            key_prefix: Prefix for the cache key
            new_ttl: New TTL in seconds
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(key_prefix, **kwargs)
        
        try:
            return bool(self.redis_client.expire(cache_key, new_ttl))
        except Exception as e:
            print(f"Error extending TTL for key {cache_key}: {e}")
            return False
    
    # Utility Operations
    
    def flush_all(self) -> bool:
        """
        Clear all data from current Redis database
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            print(f"Error flushing database: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics"""
        try:
            info = self.redis_client.info()
            return {
                "total_connections_received": info.get("total_connections_received", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "connected_clients": info.get("connected_clients", 0),
                "total_keys": self.get_cache_size()
            }
        except Exception as e:
            print(f"Error getting cache stats: {e}")
            return {}
    
    def health_check(self) -> bool:
        """Check if Redis is healthy and accessible"""
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False
    
    def close(self):
        """Close Redis connection"""
        if self.redis_client:
            self.redis_client.close()


# Singleton instance
redis_service = RedisService()