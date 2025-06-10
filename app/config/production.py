import os
from .base import BaseConfig

class ProductionConfig(BaseConfig):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    # Security - only check SECRET_KEY when actually used in production
    @property
    def SECRET_KEY(self):
        secret_key = os.getenv('SECRET_KEY')
        if os.getenv('FLASK_ENV') == 'production' and not secret_key:
            raise ValueError("SECRET_KEY environment variable must be set in production")
        return secret_key or 'production-fallback-key-change-me'
    
    # Database (if needed)
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    # Redis for caching/rate limiting
    REDIS_URL = os.getenv('REDIS_URL')
    
    # Stricter CORS - handle empty string case
    @property
    def ALLOWED_ORIGINS(self):
        origins = os.getenv('ALLOWED_ORIGINS', '')
        return origins.split(',') if origins else ['*']
    
    # Enhanced security headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
    }