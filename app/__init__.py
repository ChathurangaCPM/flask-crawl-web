from flask import Flask, jsonify
from flask_cors import CORS
import os
import logging

def create_app(config_name=None):
    """Application factory pattern with smart rate limiting"""
    app = Flask(__name__)
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['DEBUG'] = True if config_name == 'development' else False
    
    # Environment detection
    is_development = (
        app.config['DEBUG'] or 
        os.getenv('FLASK_ENV') == 'development' or
        os.getenv('ENVIRONMENT') == 'development'
    )
    
    # Additional config for crawler
    app.config['CRAWLER_TIMEOUT'] = int(os.getenv('CRAWLER_TIMEOUT', '30'))
    app.config['MAX_BATCH_SIZE'] = int(os.getenv('MAX_BATCH_SIZE', '10'))
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', '5000'))
    app.config['ALLOWED_ORIGINS'] = ['*']  # Allow all origins for development
    
    # API Key configuration
    app.config['API_KEY'] = os.getenv('API_KEY', 'dev-api-key-123')
    app.config['API_KEYS'] = os.getenv('API_KEYS', '')  # Comma-separated multiple keys
    
    # Setup CORS
    CORS(app)
    
    # Setup smart rate limiter
    try:
        from app.utils.smart_limiter import smart_limiter
        smart_limiter.init_app(app)
        app.logger.info(f"Smart rate limiter initialized - Development mode: {is_development}")
    except ImportError:
        app.logger.warning("Smart rate limiter not available - using basic setup")
    
    # Setup basic logging
    logging.basicConfig(
        level=logging.DEBUG if is_development else logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s'
    )
    
    # Create main health endpoint
    @app.route('/health')
    def main_health():
        try:
            from app.utils.smart_limiter import get_rate_limit_info
            rate_info = get_rate_limit_info()
        except ImportError:
            rate_info = {"mode": "basic", "rate_limiting": "not configured"}
        
        return jsonify({
            'status': 'healthy',
            'service': 'Multi-Purpose Crawler API',
            'version': '1.0.0',
            'environment': 'development' if is_development else 'production',
            'rate_limiting': rate_info,
            'available_services': ['web_crawler', 'ecommerce_scraper'],
            'api_key_info': {
                'bypass_available': True,
                'header_formats': ['X-API-Key', 'X-Api-Key', 'Api-Key', 'Authorization: Bearer <key>'],
                'query_param': 'api_key'
            },
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
        
        # Log registered routes
        with app.test_request_context():
            routes = []
            for rule in app.url_map.iter_rules():
                routes.append(f"{list(rule.methods)} {rule.rule}")
            app.logger.info(f"Registered {len(routes)} routes")
            
    except ImportError as e:
        app.logger.error(f"Could not import API blueprints: {e}")
        
        # Create fallback endpoints
        @app.route('/api/v1/health')
        def api_health_fallback():
            return jsonify({
                'status': 'limited',
                'service': 'Multi-Purpose Crawler API',
                'version': '1.0.0',
                'note': 'Running in fallback mode due to import errors',
                'environment': 'development' if is_development else 'production'
            })
        
        @app.route('/api/v1/crawl', methods=['POST'])
        def simple_crawl_fallback():
            return jsonify({
                'success': False,
                'error': 'Crawler service not available due to import errors',
                'message': 'Please check your dependencies and configuration'
            }), 503
    
    except Exception as e:
        app.logger.error(f"Unexpected error during blueprint registration: {e}")
    
    # Enhanced error handlers with rate limit info
    @app.errorhandler(429)
    def ratelimit_error(e):
        try:
            from app.utils.smart_limiter import get_rate_limit_info
            rate_info = get_rate_limit_info()
        except ImportError:
            rate_info = {}
        
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded',
            'message': 'Too many requests. Use an API key for unlimited access.',
            'retry_after_seconds': getattr(e, 'retry_after', 60),
            'rate_limiting': rate_info,
            'bypass_info': {
                'message': 'Add API key to bypass rate limits',
                'header': 'X-API-Key: your-api-key',
                'query': '?api_key=your-api-key'
            }
        }), 429
    
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
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500
    
    # Add route to generate API keys (development only)
    if is_development:
        @app.route('/dev/generate-api-key')
        def generate_dev_api_key():
            import secrets
            import string
            
            # Generate a random API key
            alphabet = string.ascii_letters + string.digits
            api_key = ''.join(secrets.choice(alphabet) for _ in range(32))
            
            return jsonify({
                'api_key': api_key,
                'message': 'Development API key generated',
                'usage': {
                    'header': f'X-API-Key: {api_key}',
                    'query': f'?api_key={api_key}',
                    'curl': f'curl -H "X-API-Key: {api_key}" http://localhost:5000/api/v1/crawl'
                },
                'note': 'This is for development only. In production, API keys should be securely managed.'
            })
    
    return app