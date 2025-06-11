from flask import request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
from functools import wraps

class ConditionalRateLimiter:
    """Rate limiter that respects environment and API keys"""
    
    def __init__(self, app=None):
        self.limiter = None
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the rate limiter with the Flask app"""
        # Custom key function that checks environment and API key
        def get_rate_limit_key():
            # Skip rate limiting in development
            if app.config.get('ENV', 'production') == 'development':
                return None
            
            # Check for API key
            api_key = request.headers.get('X-API-Key')
            if api_key:
                valid_api_key = app.config.get('API_KEY') or os.getenv('API_KEY', '')
                if api_key == valid_api_key and valid_api_key:
                    return None  # No rate limiting for valid API key
            
            # Default to IP-based rate limiting
            return get_remote_address()
        
        # Initialize limiter
        self.limiter = Limiter(
            app,
            key_func=get_rate_limit_key,
            default_limits=["100 per hour", "20 per minute"],
            storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://'),
            headers_enabled=True,  # Add rate limit headers to responses
            swallow_errors=False,
            in_band_error_responses=True
        )
        
        # Register error handler
        app.errorhandler(429)(self.rate_limit_exceeded_handler)
    
    def rate_limit_exceeded_handler(self, e):
        """Custom handler for rate limit exceeded"""
        # Get retry after value from the exception
        retry_after = getattr(e, 'retry_after', 60)
        
        response = jsonify({
            'success': False,
            'error': 'Rate limit exceeded',
            'message': 'Too many requests. Please try again later or use an API key for unlimited access.',
            'details': {
                'retry_after_seconds': retry_after,
                'api_key_header': 'X-API-Key',
                'rate_limit_info': {
                    'environment': os.getenv('FLASK_ENV', 'production'),
                    'documentation': '/api/v1/docs',
                    'contact': 'support@infinitude.lk'
                }
            }
        })
        
        # Add rate limit headers
        response.headers['Retry-After'] = str(retry_after)
        response.headers['X-RateLimit-Limit'] = str(e.limit.limit)
        response.headers['X-RateLimit-Remaining'] = '0'
        response.headers['X-RateLimit-Reset'] = str(e.limit.reset_at)
        
        return response, 429
    
    def conditional_limit(self, limit_string):
        """Decorator that applies rate limiting conditionally"""
        def decorator(f):
            # If we're in development, don't apply rate limiting
            if os.getenv('FLASK_ENV', 'production') == 'development':
                return f
            
            # Otherwise, apply the limiter
            return self.limiter.limit(limit_string)(f)
        
        return decorator
    
    def exempt_when_authenticated(self, f):
        """Decorator to exempt authenticated requests from rate limiting"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if request has valid API key
            api_key = request.headers.get('X-API-Key')
            valid_api_key = current_app.config.get('API_KEY') or os.getenv('API_KEY', '')
            
            if api_key and api_key == valid_api_key and valid_api_key:
                # Mark request as exempt from rate limiting
                request.environ['RATE_LIMIT_EXEMPT'] = True
            
            return f(*args, **kwargs)
        
        return decorated_function

# Create a helper function for checking rate limit status
def check_rate_limit_status():
    """Check current rate limit status for the request"""
    is_development = os.getenv('FLASK_ENV', 'production') == 'development'
    api_key = request.headers.get('X-API-Key')
    valid_api_key = current_app.config.get('API_KEY') or os.getenv('API_KEY', '')
    has_valid_key = api_key and api_key == valid_api_key and valid_api_key != ''
    
    return {
        'rate_limiting_active': not is_development and not has_valid_key,
        'environment': os.getenv('FLASK_ENV', 'production'),
        'is_development': is_development,
        'has_api_key': bool(api_key),
        'api_key_valid': has_valid_key,
        'exempt': is_development or has_valid_key
    }