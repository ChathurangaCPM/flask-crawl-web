from .base import BaseConfig

class DevelopmentConfig(BaseConfig):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    
    # Relaxed settings for development
    RATELIMIT_DEFAULT = "1000 per hour"
    ALLOWED_ORIGINS = ['*']