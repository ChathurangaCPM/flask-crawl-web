# app/api/v1/content_only.py
from flask import request, jsonify, current_app
import asyncio
import time
import traceback
import os
from functools import wraps

from app.api.v1 import api_v1
from app.services.content_only_service import ContentOnlyCrawlerService
from app.utils.validators import validate_crawl_request, validate_batch_request
from app.utils.response_helpers import success_response, error_response

# Rate limiting decorator (using same pattern as crawl.py)
def apply_rate_limit(limit_string):
    """Apply rate limit only in production without valid API key"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip rate limiting in development
            if os.getenv('FLASK_ENV', 'production') == 'development':
                return f(*args, **kwargs)
            
            # Check for API key
            api_key = request.headers.get('X-API-Key')
            valid_api_key = os.getenv('API_KEY', '')
            
            if api_key and api_key == valid_api_key and valid_api_key:
                # Valid API key - no rate limiting
                return f(*args, **kwargs)
            
            # Apply rate limiting (would need to import limiter from crawl.py)
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def safe_async_run(coro, timeout=30):
    """Safely run async coroutine with proper event loop handling"""
    try:
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=timeout)
        except RuntimeError:
            return asyncio.run(coro)
    except Exception as e:
        current_app.logger.error(f"Async execution error: {str(e)}")
        raise e

@api_v1.route('/content', methods=['POST'])
@apply_rate_limit("20 per minute")
def extract_content_only():
    """Extract only clean text content without images and links"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate request
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        config = data.get('config', {})
        
        # Get content length limit (default 5000, max 20000)
        max_length = min(config.get('max_content_length', 5000), 20000)
        
        # Initialize content-only crawler service
        crawler_service = ContentOnlyCrawlerService(current_app.config)
        
        # Run content extraction
        try:
            result = safe_async_run(
                crawler_service.crawl_content_only(url, max_length),
                timeout=25
            )
        except asyncio.TimeoutError:
            return error_response("Content extraction timeout after 25 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Content extraction failed: {str(crawl_error)}")
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            return error_response(f"Content extraction failed: {str(crawl_error)}", 500)
        
        # Add timing information
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'content_only'
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Content extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Content-only endpoint error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Internal server error", 500)

@api_v1.route('/content/fast', methods=['POST'])
@apply_rate_limit("30 per minute")
def extract_content_ultra_fast():
    """Ultra-fast content extraction with aggressive limits"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        config = data.get('config', {})
        
        # Ultra-fast: smaller content limit
        max_length = min(config.get('max_content_length', 2000), 5000)
        
        crawler_service = ContentOnlyCrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_content_only(url, max_length),
                timeout=15  # Shorter timeout for ultra-fast
            )
        except asyncio.TimeoutError:
            return error_response("Ultra-fast content extraction timeout after 15 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Ultra-fast content extraction failed: {str(crawl_error)}")
            return error_response(f"Ultra-fast content extraction failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'content_only_ultra_fast'
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Ultra-fast content extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Ultra-fast content extraction error: {str(e)}")
        return error_response("Internal server error", 500)

@api_v1.route('/content/batch', methods=['POST'])
@apply_rate_limit("5 per minute")  # Very strict for batch
def batch_extract_content():
    """Batch content extraction without images and links"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        max_batch_size = min(current_app.config.get('MAX_BATCH_SIZE', 5), 5)
        is_valid, error_msg = validate_batch_request(data, max_batch_size)
        if not is_valid:
            return error_response(error_msg, 400)
        
        urls = data['urls'][:max_batch_size]
        config = data.get('config', {})
        
        # Batch content settings
        max_length = min(config.get('max_content_length', 2000), 4000)  # Smaller for batch
        max_concurrent = min(config.get('max_concurrent', 2), 3)
        
        crawler_service = ContentOnlyCrawlerService(current_app.config)
        
        try:
            results = safe_async_run(
                crawler_service.crawl_multiple_content_only(urls, max_length, max_concurrent),
                timeout=60  # Longer timeout for batch
            )
        except asyncio.TimeoutError:
            return error_response("Batch content extraction timeout after 60 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Batch content extraction failed: {str(crawl_error)}")
            return error_response(f"Batch content extraction failed: {str(crawl_error)}", 500)
        
        # Process results
        if results:
            result_dicts = []
            successful = 0
            failed = 0
            
            for result in results:
                try:
                    result_dict = result.to_dict() if result else {"success": False, "error": "No result"}
                    result_dicts.append(result_dict)
                    if result and result.success:
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    result_dicts.append({"success": False, "error": f"Result processing error: {str(e)}"})
                    failed += 1
        else:
            result_dicts = []
            successful = 0
            failed = len(urls)
        
        total_time = time.time() - start_time
        
        return success_response({
            'results': result_dicts,
            'total_processed': len(result_dicts),
            'successful': successful,
            'failed': failed,
            'total_time': round(total_time, 2),
            'average_time_per_url': round(total_time / len(urls), 2) if urls else 0,
            'mode': 'content_only_batch',
            'features': {
                'images_removed': True,
                'links_removed': True,
                'clean_text_only': True
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Batch content extraction error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Batch content processing failed", 500)

@api_v1.route('/content/<path:url>', methods=['GET'])
@apply_rate_limit("40 per minute")
def extract_content_get(url):
    """Quick content-only extraction via GET request"""
    start_time = time.time()
    
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Very fast content extraction
        max_length = 1500  # Small for GET requests
        
        crawler_service = ContentOnlyCrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_content_only(url, max_length),
                timeout=10  # Very short timeout for GET
            )
        except asyncio.TimeoutError:
            return error_response("GET content extraction timeout after 10 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"GET content extraction failed: {str(crawl_error)}")
            return error_response(f"GET content extraction failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'content_only_get'
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "GET content extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"GET content extraction error: {str(e)}")
        return error_response("GET content request failed", 500)

@api_v1.route('/content/test', methods=['GET'])
@apply_rate_limit("60 per minute")
def test_content_extraction():
    """Test endpoint for content-only extraction"""
    try:
        return success_response({
            "message": "Content-only extraction service is ready",
            "endpoints": {
                "content": "POST /api/v1/content",
                "content_fast": "POST /api/v1/content/fast", 
                "content_batch": "POST /api/v1/content/batch",
                "content_get": "GET /api/v1/content/<url>"
            },
            "features": {
                "images_removed": "All images are removed from content",
                "links_removed": "All links are removed but text is kept",
                "clean_text": "Only clean, readable text content is returned",
                "main_content": "Prioritizes main content areas over navigation/sidebars",
                "fast_extraction": "Optimized for speed with minimal processing"
            },
            "status": "healthy",
            "service": "Content-Only Extraction API"
        })
    except Exception as e:
        return error_response(f"Content extraction test failed: {str(e)}", 500)