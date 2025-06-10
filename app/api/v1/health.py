from flask import jsonify, current_app
from app.api.v1 import api_v1
from app.utils.response_helpers import success_response
import time
import os

@api_v1.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return success_response({
        'status': 'healthy',
        'service': current_app.config.get('API_TITLE', 'Web Crawler API'),
        'version': current_app.config.get('API_VERSION', 'v1'),
        'environment': current_app.config.get('ENV', 'development'),
        'timestamp': time.time()
    })

@api_v1.route('/health/detailed', methods=['GET'])
def detailed_health_check():
    """Detailed health check with system info"""
    try:
        import psutil
        
        system_info = {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'process_id': os.getpid()
        }
    except ImportError:
        system_info = {
            'process_id': os.getpid(),
            'note': 'psutil not available for detailed system metrics'
        }
    
    return success_response({
        'status': 'healthy',
        'service': current_app.config.get('API_TITLE', 'Web Crawler API'),
        'version': current_app.config.get('API_VERSION', 'v1'),
        'environment': current_app.config.get('ENV', 'development'),
        'system': system_info,
        'timestamp': time.time()
    })