from flask import request, jsonify, current_app
import time
import logging

logger = logging.getLogger(__name__)

def setup_middleware(app):
    """Setup application middleware"""
    
    @app.before_request
    def before_request():
        """Before request middleware"""
        request.start_time = time.time()
        
        # Log request
        logger.info(f"{request.method} {request.url} - {request.remote_addr}")
    
    @app.after_request
    def after_request(response):
        """After request middleware"""
        # Add response time header
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            response.headers['X-Response-Time'] = f"{duration:.3f}s"
        
        # Add security headers
        if hasattr(current_app.config, 'SECURITY_HEADERS'):
            for header, value in current_app.config['SECURITY_HEADERS'].items():
                response.headers[header] = value
        
        # Log response
        logger.info(f"{request.method} {request.url} - {response.status_code}")
        
        return response
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'error': 'Endpoint not found'
        }), 404
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            'success': False,
            'error': 'Method not allowed'
        }), 405
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {str(error)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500