from .base import BaseConfig

class TestingConfig(BaseConfig):
    """Testing configuration"""
    DEBUG = False
    TESTING = True
    
    # Use in-memory storage for tests
    RATELIMIT_STORAGE_URL = 'memory://'
    
    # Disable rate limiting for tests
    RATELIMIT_DEFAULT = "10000 per hour"
    
    # Faster timeouts for tests
    CRAWLER_TIMEOUT = 5
    MAX_BATCH_SIZE = 3