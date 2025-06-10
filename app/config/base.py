import os
from datetime import timedelta

class BaseConfig:
    """Base configuration class"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # API Configuration
    API_TITLE = 'Web Crawler API'
    API_VERSION = 'v1'
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')
    RATELIMIT_DEFAULT = "100 per hour"
    
    # Crawler settings
    CRAWLER_TIMEOUT = int(os.getenv('CRAWLER_TIMEOUT', '30'))
    MAX_BATCH_SIZE = int(os.getenv('MAX_BATCH_SIZE', '10'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', '5014'))
    
    # CORS
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')