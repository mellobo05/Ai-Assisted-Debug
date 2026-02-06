"""
Redis caching service for frequently accessed data.
Requires: pip install redis
"""
import json
import hashlib
import os
from typing import Optional, Dict, Any
from functools import wraps

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("[CACHE] Redis not available. Install with: pip install redis")


class CacheService:
    """Simple Redis-based caching service"""
    
    def __init__(self):
        if not REDIS_AVAILABLE:
            self.client = None
            return
            
        try:
            self.client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                db=int(os.getenv("REDIS_DB", 0)),
                decode_responses=True,
                socket_connect_timeout=2,  # Fast fail if Redis unavailable
            )
            # Test connection
            self.client.ping()
            print("[CACHE] Redis connection established")
        except Exception as e:
            print(f"[CACHE] Redis connection failed: {e}. Caching disabled.")
            self.client = None
    
    def _make_key(self, prefix: str, **kwargs) -> str:
        """Generate cache key from parameters"""
        if not kwargs:
            return prefix
        key_str = json.dumps(kwargs, sort_keys=True)
        hash_str = hashlib.md5(key_str.encode()).hexdigest()[:16]
        return f"{prefix}:{hash_str}"
    
    def get(self, prefix: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get cached value"""
        if not self.client:
            return None
        
        try:
            key = self._make_key(prefix, **kwargs)
            cached = self.client.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"[CACHE] Get error: {e}")
        return None
    
    def set(self, prefix: str, value: Dict[str, Any], ttl: int = 3600, **kwargs):
        """Set cached value with TTL"""
        if not self.client:
            return
        
        try:
            key = self._make_key(prefix, **kwargs)
            self.client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            print(f"[CACHE] Set error: {e}")
    
    def delete(self, prefix: str, **kwargs):
        """Delete cached value"""
        if not self.client:
            return
        
        try:
            key = self._make_key(prefix, **kwargs)
            self.client.delete(key)
        except Exception as e:
            print(f"[CACHE] Delete error: {e}")
    
    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern (use with caution)"""
        if not self.client:
            return
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                self.client.delete(*keys)
        except Exception as e:
            print(f"[CACHE] Clear pattern error: {e}")


# Global cache instance
_cache_service = CacheService()


def cached(prefix: str, ttl: int = 3600):
    """
    Decorator for caching function results.
    
    Usage:
        @cached("analysis", ttl=7200)
        def analyze_issue(issue_key: str, summary: str):
            # ... expensive operation ...
            return result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function args
            cache_key_kwargs = {}
            if args:
                # Use function parameter names if available
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                for i, arg in enumerate(args):
                    if i < len(param_names):
                        cache_key_kwargs[param_names[i]] = str(arg)
            
            cache_key_kwargs.update({k: str(v) for k, v in kwargs.items()})
            
            # Try cache first
            cached_result = _cache_service.get(prefix, **cache_key_kwargs)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            if result is not None:
                _cache_service.set(prefix, result, ttl=ttl, **cache_key_kwargs)
            
            return result
        return wrapper
    return decorator


# Convenience functions for common use cases
def get_cached_analysis(issue_key: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
    """Get cached analysis result"""
    return _cache_service.get("analysis", issue_key=issue_key, idem=idempotency_key)


def set_cached_analysis(issue_key: str, idempotency_key: str, result: Dict[str, Any], ttl: int = 3600):
    """Cache analysis result"""
    _cache_service.set("analysis", result, ttl=ttl, issue_key=issue_key, idem=idempotency_key)


def get_cached_embedding(text: str, provider: str, model_name: str) -> Optional[list]:
    """Get cached embedding"""
    cached = _cache_service.get("embedding", text=text, provider=provider, model=model_name)
    return cached.get("embedding") if cached else None


def set_cached_embedding(text: str, provider: str, model_name: str, embedding: list, ttl: int = 86400):
    """Cache embedding (longer TTL since embeddings don't change)"""
    _cache_service.set(
        "embedding",
        {"embedding": embedding},
        ttl=ttl,
        text=text,
        provider=provider,
        model=model_name,
    )
