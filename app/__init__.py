from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging

def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['DEBUG'] = True if config_name == 'development' else False
    
    # Additional config for crawler
    app.config['CRAWLER_TIMEOUT'] = int(os.getenv('CRAWLER_TIMEOUT', '30'))
    app.config['MAX_BATCH_SIZE'] = int(os.getenv('MAX_BATCH_SIZE', '10'))
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', '5000'))
    app.config['ALLOWED_ORIGINS'] = ['*']  # Allow all origins for development
    app.config['BYPASS_API_KEY'] = os.getenv('BYPASS_API_KEY')
    
    # Rate limiting configuration - Use in-memory storage (no Redis required)
    app.config['RATELIMIT_STORAGE_URL'] = 'memory://'
    app.config['RATELIMIT_DEFAULT'] = os.getenv('RATELIMIT_DEFAULT', '100 per hour')
    
    # Setup CORS
    CORS(app)
    
    # Setup rate limiter with in-memory storage
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[app.config['RATELIMIT_DEFAULT']],
        storage_uri='memory://',  # Force in-memory storage
        strategy='fixed-window'  # Simple strategy for in-memory
    )
    
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)
    
    # Create fallback health endpoint
    @app.route('/health')
    def simple_health():
        return jsonify({
            'status': 'healthy',
            'service': 'Multi-Purpose Crawler API',
            'version': '1.0.0',
            'available_services': ['web_crawler', 'ecommerce_scraper'],
            'rate_limiting': 'in-memory',
            'message': 'All services operational'
        })
    
    # Try to import and register blueprints
    try:
        # Register original crawler API
        from app.api.v1 import api_v1
        app.register_blueprint(api_v1, url_prefix='/api/v1')
        app.logger.info("Successfully registered Web Crawler API v1 blueprint")
        
        # Register separate e-commerce API
        try:
            from app.api.v1.ecommerce import ecommerce_bp
            app.register_blueprint(ecommerce_bp, url_prefix='/api/v1/ecommerce')
            app.logger.info("Successfully registered E-commerce Scraper API blueprint")
        except ImportError as e:
            app.logger.warning(f"E-commerce blueprint not available: {e}")
        
        # Initialize rate limiter with the blueprints
        limiter.init_app(app)
        
        # Test if the blueprint endpoints are working
        with app.test_request_context():
            routes = []
            for rule in app.url_map.iter_rules():
                routes.append(f"{rule.methods} {rule.rule}")
            app.logger.info(f"Registered routes: {len(routes)} total")
            
    except ImportError as e:
        app.logger.error(f"Could not import API blueprints: {e}")
        
        # Create simple endpoints as fallback
        @app.route('/api/v1/health')
        @limiter.limit("50 per minute")
        def api_health():
            return jsonify({
                'status': 'healthy',
                'service': 'Multi-Purpose Crawler API',
                'version': '1.0.0',
                'note': 'Running in fallback mode due to import errors'
            })
        
        @app.route('/api/v1/crawl', methods=['POST'])
        @limiter.limit("5 per minute")
        def simple_crawl():
            return jsonify({
                'success': False,
                'error': 'Crawler service not available due to import errors',
                'message': 'Please check your dependencies and configuration'
            }), 503
    
    except Exception as e:
        app.logger.error(f"Unexpected error during blueprint registration: {e}")
    
    # Global rate limit exceeded handler
    @app.errorhandler(429)
    def ratelimit_error(e):
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded',
            'message': 'Too many requests. Please try again later.',
            'retry_after_seconds': getattr(e, 'retry_after', 60)
        }), 429
    
    # Global 404 handler
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({
            'success': False,
            'error': 'Endpoint not found',
            'message': 'The requested endpoint does not exist',
            'available_endpoints': {
                'web_crawler': '/api/v1/',
                'ecommerce': '/api/v1/ecommerce/',
                'health': '/health'
            }
        }), 404
    
    # Global error handler
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500
    
    return app