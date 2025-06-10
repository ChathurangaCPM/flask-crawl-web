from flask import Flask, jsonify
from flask_cors import CORS
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
    
    # Setup CORS
    CORS(app)
    
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)
    
    # Create fallback health endpoint
    @app.route('/health')
    def simple_health():
        return jsonify({
            'status': 'healthy',
            'service': 'Web Crawler API',
            'version': '1.0.0',
            'message': 'Fallback health endpoint'
        })
    
    # Try to import and register blueprints
    try:
        from app.api.v1 import api_v1
        app.register_blueprint(api_v1, url_prefix='/api/v1')
        app.logger.info("Successfully registered API v1 blueprint")
        
        # Test if the blueprint endpoints are working
        with app.test_request_context():
            routes = []
            for rule in app.url_map.iter_rules():
                routes.append(f"{rule.methods} {rule.rule}")
            app.logger.info(f"Registered routes: {routes}")
            
    except ImportError as e:
        app.logger.error(f"Could not import API blueprint: {e}")
        
        # Create simple endpoints as fallback
        @app.route('/api/v1/health')
        def api_health():
            return jsonify({
                'status': 'healthy',
                'service': 'Web Crawler API',
                'version': '1.0.0',
                'note': 'Running in fallback mode due to import errors'
            })
        
        @app.route('/api/v1/crawl', methods=['POST'])
        def simple_crawl():
            return jsonify({
                'success': False,
                'error': 'Crawler service not available due to import errors',
                'message': 'Please check your dependencies and configuration'
            }), 503
    
    except Exception as e:
        app.logger.error(f"Unexpected error during blueprint registration: {e}")
    
    return app