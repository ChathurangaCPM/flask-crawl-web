from flask import Flask
from flask_cors import CORS
import os

def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['DEBUG'] = True if config_name == 'development' else False
    
    # Setup CORS
    CORS(app)
    
    # Import and register blueprints
    try:
        from app.api.v1 import api_v1
        app.register_blueprint(api_v1, url_prefix='/api/v1')
    except ImportError as e:
        print(f"Warning: Could not import API blueprint: {e}")
        # Create a simple health endpoint if blueprints fail
        @app.route('/health')
        def health():
            return {'status': 'healthy', 'service': 'Web Crawler API'}
    
    return app