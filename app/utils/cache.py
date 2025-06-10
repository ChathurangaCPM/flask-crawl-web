import hashlib
import json
import time
from typing import Any, Optional

class SimpleCache:
    """Simple in-memory cache implementation"""
    
    def __init__(self, default_ttl: int = 3600):
        self._cache = {}
        self.default_ttl = default_ttl
    
    def _make_key(self, key: str) -> str:
        """Create a hash key from string"""
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        cache_key = self._make_key(key)
        
        if cache_key in self._cache:
            value, expiry = self._cache[cache_key]
            if expiry > time.time():
                return value
            else:
                # Remove expired entry
                del self._cache[cache_key]
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache"""
        cache_key = self._make_key(key)
        expiry = time.time() + (ttl or self.default_ttl)
        self._cache[cache_key] = (value, expiry)
    
    def delete(self, key: str) -> None:
        """Delete value from cache"""
        cache_key = self._make_key(key)
        if cache_key in self._cache:
            del self._cache[cache_key]
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
    
    def cleanup_expired(self) -> None:
        """Remove expired entries"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry <= current_time
        ]
        
        for key in expired_keys:
            del self._cache[key]

# Global cache instance
cache = SimpleCache()

def cache_key_for_url(url: str, config: dict = None) -> str:
    """Generate cache key for URL and config"""
    config_str = json.dumps(config or {}, sort_keys=True)
    return f"crawl:{url}:{hashlib.md5(config_str.encode()).hexdigest()}"