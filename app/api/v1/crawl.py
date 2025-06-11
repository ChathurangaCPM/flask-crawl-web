from flask import request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import asyncio
import time
import sys
import traceback
from app.api.v1 import api_v1
from app.services.crawler_service import CrawlerService
from app.models.crawler_models import CrawlConfig
from app.utils.validators import validate_crawl_request, validate_batch_request
from app.utils.response_helpers import success_response, error_response
from app.utils.smart_limiter import smart_limit, get_rate_limit_info

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour", "20 per minute"],
    storage_uri="memory://",
)

def safe_async_run(coro, timeout=30):
    """Safely run async coroutine with proper event loop handling"""
    try:
        # Try to get existing event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an event loop, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=timeout)
        except RuntimeError:
            # No running loop, safe to create new one
            return asyncio.run(coro)
    except Exception as e:
        current_app.logger.error(f"Async execution error: {str(e)}")
        raise e
@api_v1.route('/crawl', methods=['POST'])
@smart_limit("15 per minute")  # Only applies in production with no API key
def crawl_url():
    """High-speed single URL crawling endpoint with smart rate limiting"""
    start_time = time.time()
    
    try:
        # Add rate limit info to response metadata
        rate_info = get_rate_limit_info()
        
        data = request.get_json()
        
        # Validate request
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        config_data = data.get('config', {})
        
        # Create crawl configuration with safe defaults
        crawl_config = CrawlConfig(
            word_count_threshold=max(1, config_data.get('word_count_threshold', 5)),
            excluded_tags=config_data.get('excluded_tags', ['form', 'header', 'nav', 'footer']),
            exclude_external_links=config_data.get('exclude_external_links', True),
            process_iframes=False,
            remove_overlay_elements=config_data.get('remove_overlay_elements', True),
            use_cache=config_data.get('use_cache', True),
            max_content_length=min(config_data.get('max_content_length', 5000), 20000),
            
            # Speed optimization options
            speed_mode='fast',
            skip_images=config_data.get('skip_images', True),
            skip_links=config_data.get('skip_links', False),
            minimal_processing=config_data.get('minimal_processing', False)
        )
        
        # Initialize crawler service
        crawler_service = CrawlerService(current_app.config)
        
        # Run crawling with timeout
        try:
            result = safe_async_run(
                crawler_service.crawl_single_url(url, crawl_config),
                timeout=30
            )
        except asyncio.TimeoutError:
            return error_response("Request timeout after 30 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Crawl execution failed: {str(crawl_error)}")
            return error_response(f"Crawl failed: {str(crawl_error)}", 500)
        
        # Add timing information and rate limit info
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['rate_limiting'] = rate_info
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Unknown error occurred"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Crawl endpoint error: {str(e)}")
        return error_response("Internal server error", 500)

@api_v1.route('/crawl/fast', methods=['POST'])
@smart_limit("20 per minute")
def crawl_url_ultra_fast():
    """Ultra-fast crawling with minimal processing"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        config_data = data.get('config', {})
        
        # Ultra-fast configuration
        crawl_config = CrawlConfig(
            word_count_threshold=3,
            excluded_tags=['form', 'header', 'nav', 'footer', 'script', 'style', 'noscript'],
            exclude_external_links=True,
            process_iframes=False,
            remove_overlay_elements=True,
            use_cache=True,
            max_content_length=min(config_data.get('max_content_length', 2000), 5000),
            speed_mode='fast',
            skip_images=True,
            skip_links=True,
            minimal_processing=True
        )
        
        crawler_service = CrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_single_url_fast(url, crawl_config),
                timeout=15
            )
        except asyncio.TimeoutError:
            return error_response("Fast crawl timeout after 15 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Fast crawl failed: {str(crawl_error)}")
            return error_response(f"Fast crawl failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['mode'] = 'ultra_fast'
                result.metadata['rate_limiting'] = rate_info
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Fast crawl failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Fast crawl error: {str(e)}")
        return error_response("Internal server error", 500)

@api_v1.route('/crawl/batch', methods=['POST'])
@smart_limit("3 per minute")  # Very strict for batch
def batch_crawl():
    """High-speed batch URL crawling with concurrency"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        max_batch_size = min(current_app.config.get('MAX_BATCH_SIZE', 5), 5)
        is_valid, error_msg = validate_batch_request(data, max_batch_size)
        if not is_valid:
            return error_response(error_msg, 400)
        
        urls = data['urls'][:max_batch_size]
        config_data = data.get('config', {})
        
        # Batch-optimized configuration
        crawl_config = CrawlConfig(
            word_count_threshold=5,
            excluded_tags=['form', 'header', 'nav', 'footer', 'script', 'style'],
            exclude_external_links=True,
            process_iframes=False,
            remove_overlay_elements=True,
            use_cache=True,
            max_content_length=min(config_data.get('max_content_length', 2000), 3000),
            speed_mode='fast',
            max_concurrent=min(config_data.get('max_concurrent', 2), 3),
            skip_images=True,
            skip_links=config_data.get('skip_links', True)
        )
        
        crawler_service = CrawlerService(current_app.config)
        
        try:
            results = safe_async_run(
                crawler_service.crawl_multiple_urls(urls, crawl_config),
                timeout=60
            )
        except asyncio.TimeoutError:
            return error_response("Batch crawl timeout after 60 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Batch crawl failed: {str(crawl_error)}")
            return error_response(f"Batch crawl failed: {str(crawl_error)}", 500)
        
        # Convert results and add timing
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
            'mode': 'concurrent_batch',
            'rate_limiting': rate_info
        })
        
    except Exception as e:
        current_app.logger.error(f"Batch crawl error: {str(e)}")
        return error_response("Batch processing failed", 500)

@api_v1.route('/crawl/<path:url>', methods=['GET'])
@smart_limit("30 per minute")
def crawl_get_endpoint(url):
    """Lightning-fast GET endpoint"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Ultra-minimal config for GET requests
        crawl_config = CrawlConfig(
            max_content_length=1500,
            speed_mode='fast',
            skip_images=True,
            skip_links=True,
            minimal_processing=True,
            excluded_tags=['form', 'header', 'nav', 'footer', 'script', 'style'],
            word_count_threshold=3
        )
        
        crawler_service = CrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_single_url_fast(url, crawl_config),
                timeout=10
            )
        except asyncio.TimeoutError:
            return error_response("GET crawl timeout after 10 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"GET crawl failed: {str(crawl_error)}")
            return error_response(f"GET crawl failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['mode'] = 'get_fast'
                result.metadata['rate_limiting'] = rate_info
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "GET crawl failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"GET crawl error: {str(e)}")
        return error_response("GET request failed", 500)

# Enhanced health check with rate limiting info
@api_v1.route('/health', methods=['GET'])
@smart_limit("60 per minute")
def health_check():
    """Enhanced health check with rate limiting information"""
    try:
        rate_info = get_rate_limit_info()
        
        return success_response({
            "status": "healthy",
            "service": "Web Crawler API",
            "version": "1.0.0",
            "rate_limiting": rate_info,
            "endpoints": {
                "single": "POST /api/v1/crawl",
                "fast": "POST /api/v1/crawl/fast", 
                "batch": "POST /api/v1/crawl/batch",
                "get": "GET /api/v1/crawl/<url>",
                "health": "GET /api/v1/health"
            },
            "api_key_info": {
                "bypass_available": True,
                "development_keys": ["dev-api-key-123", "development-unlimited-access"] if rate_info.get("mode") == "development" else None,
                "header_formats": ["X-API-Key", "X-Api-Key", "Api-Key"],
                "query_param": "api_key"
            }
        })
    except Exception as e:
        return error_response(f"Health check failed: {str(e)}", 500)

# Enhanced test endpoint
@api_v1.route('/test', methods=['GET'])
@smart_limit("60 per minute")
def test_crawler():
    """Enhanced test endpoint with rate limiting examples"""
    try:
        rate_info = get_rate_limit_info()
        
        response_data = {
            "message": "Crawler service is ready",
            "rate_limiting": rate_info,
            "endpoints": {
                "single": "POST /api/v1/crawl",
                "fast": "POST /api/v1/crawl/fast", 
                "batch": "POST /api/v1/crawl/batch",
                "get": "GET /api/v1/crawl/<url>"
            },
            "examples": {
                "basic_crawl": {
                    "url": "POST /api/v1/crawl",
                    "payload": {
                        "url": "https://example.com",
                        "config": {"max_content_length": 2000}
                    }
                },
                "with_api_key": {
                    "headers": {"X-API-Key": "your-api-key"},
                    "note": "Bypasses rate limits"
                }
            },
            "status": "healthy"
        }
        
        # Add development-specific info
        if rate_info.get("mode") == "development":
            response_data["development_info"] = {
                "rate_limiting": "disabled",
                "test_api_keys": ["dev-api-key-123", "development-unlimited-access"],
                "generate_key": "GET /dev/generate-api-key"
            }
        
        return success_response(response_data)
    except Exception as e:
        return error_response(f"Test failed: {str(e)}", 500)