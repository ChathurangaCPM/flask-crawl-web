from flask import request, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
import os
import hashlib
import secrets
import string

class SmartRateLimiter:
    """Smart rate limiter with API key bypass and environment-based configuration"""
    
    def __init__(self, app=None):
        self.app = app
        self.limiter = None
        self.valid_api_keys = set()
        self.development_mode = False
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the rate limiter with the Flask app"""
        self.app = app
        
        # Determine if we're in development mode
        self.development_mode = (
            app.config.get('DEBUG', False) or
            os.getenv('FLASK_ENV') == 'development' or
            os.getenv('ENVIRONMENT') == 'development'
        )
        
        # Load API keys from environment or config
        self._load_api_keys()
        
        # Configure rate limiter based on environment
        if self.development_mode:
            app.logger.info("🚀 Development mode detected - Rate limiting DISABLED")
            # In development, create a minimal limiter for structure but don't enforce limits
            self.limiter = Limiter(
                app=app,
                key_func=self.get_rate_limit_key,
                default_limits=[],  # No default limits in development
                storage_uri="memory://",
                strategy="fixed-window",
                headers_enabled=True
            )
        else:
            app.logger.info("🔒 Production mode - Rate limiting ENABLED with API key bypass")
            # In production, use actual rate limiting
            self.limiter = Limiter(
                app=app,
                key_func=self.get_rate_limit_key,
                default_limits=["200 per hour", "50 per minute"],
                storage_uri="memory://",
                strategy="fixed-window",
                headers_enabled=True
            )
        
        # Store reference in app for access in routes
        app.smart_limiter = self
    
    def _load_api_keys(self):
        """Load valid API keys from environment variables"""
        # Single API key
        api_key = os.getenv('API_KEY') or os.getenv('BYPASS_API_KEY')
        if api_key:
            self.valid_api_keys.add(api_key)
        
        # Multiple API keys (comma-separated)
        api_keys_str = os.getenv('API_KEYS', '')
        if api_keys_str:
            keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
            self.valid_api_keys.update(keys)
        
        # Predefined API keys for development
        if self.development_mode:
            dev_keys = [
                'dev-api-key-123',
                'development-unlimited-access',
                'test-key-no-limits',
                'local-dev-bypass'
            ]
            self.valid_api_keys.update(dev_keys)
        
        if self.valid_api_keys:
            self.app.logger.info(f"🔑 Loaded {len(self.valid_api_keys)} API keys for rate limit bypass")
        else:
            self.app.logger.warning("⚠️  No API keys configured - all requests will be rate limited in production")
    
    def get_rate_limit_key(self):
        """Custom key function that checks for API key bypass"""
        # Check for API key in headers
        api_key = self.get_api_key_from_request()
        
        if api_key and self.is_valid_api_key(api_key):
            # Return a special key that bypasses rate limiting
            return f"unlimited-{hashlib.md5(api_key.encode()).hexdigest()[:8]}"
        
        # Standard rate limiting by IP
        return get_remote_address()
    
    def get_api_key_from_request(self):
        """Extract API key from request headers or query parameters"""
        # Check various header formats
        api_key = (
            request.headers.get('X-API-Key') or
            request.headers.get('X-Api-Key') or
            request.headers.get('Api-Key') or
            request.headers.get('API-Key') or
            request.headers.get('Authorization', '').replace('Bearer ', '').replace('Api-Key ', '') or
            request.args.get('api_key') or
            request.args.get('apikey') or
            request.form.get('api_key') if request.form else None
        )
        
        return api_key.strip() if api_key else None
    
    def is_valid_api_key(self, api_key):
        """Check if the provided API key is valid"""
        return api_key in self.valid_api_keys
    
    def is_request_unlimited(self):
        """Check if the current request should bypass rate limiting"""
        if self.development_mode:
            return True
        
        api_key = self.get_api_key_from_request()
        return api_key and self.is_valid_api_key(api_key)
    
    def limit(self, limit_string):
        """Decorator for applying rate limits with smart bypass"""
        def decorator(f):
            if self.development_mode:
                # In development, just return the function without any limiting
                @wraps(f)
                def wrapped(*args, **kwargs):
                    return f(*args, **kwargs)
                return wrapped
            
            # In production, apply conditional rate limiting
            @wraps(f)
            def wrapped(*args, **kwargs):
                # Check for API key bypass
                if self.is_request_unlimited():
                    return f(*args, **kwargs)
                
                # Apply rate limiting using the actual limiter
                if self.limiter:
                    # Create a temporary decorated function with the limit
                    limited_func = self.limiter.limit(limit_string)(f)
                    return limited_func(*args, **kwargs)
                
                # Fallback: no limiting
                return f(*args, **kwargs)
            
            return wrapped
        return decorator
    
    def exempt(self, f):
        """Decorator to completely exempt a route from rate limiting"""
        @wraps(f)
        def wrapped(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapped
    
    def generate_api_key(self, length=32):
        """Generate a secure API key"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

# Global rate limiter instance
smart_limiter = SmartRateLimiter()

def get_rate_limit_info():
    """Get current rate limiting information for API responses"""
    if smart_limiter.development_mode:
        return {
            "mode": "development",
            "rate_limiting": "disabled",
            "unlimited_access": True,
            "message": "No rate limits in development mode"
        }
    
    api_key = smart_limiter.get_api_key_from_request()
    if api_key and smart_limiter.is_valid_api_key(api_key):
        return {
            "mode": "production",
            "rate_limiting": "bypassed",
            "unlimited_access": True,
            "api_key": "valid",
            "message": "Rate limits bypassed with valid API key"
        }
    
    return {
        "mode": "production", 
        "rate_limiting": "active",
        "unlimited_access": False,
        "limits": {
            "default": "200 per hour, 50 per minute",
            "crawl": "15 per minute",
            "ecommerce": "5 per minute"
        },
        "message": "Rate limits active - use API key for unlimited access"
    }

def smart_limit(limit_string):
    """Convenient decorator function for smart rate limiting"""
    return smart_limiter.limit(limit_string)

def exempt_from_limits(f):
    """Convenient decorator function to exempt from rate limiting"""
    return smart_limiter.exempt(f)