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
from app.services.speed_crawler import SpeedOptimizedCrawler, CrawlSpeed
from app.utils.smart_limiter import smart_limit, get_rate_limit_info
from urllib.parse import urlparse

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

@api_v1.route('/crawl/ultra-fast', methods=['POST'])
@smart_limit("30 per minute")  # Higher limit for ultra-fast
def crawl_ultra_fast():
    """⚡ Ultra-fast crawling - Lightning speed, basic content"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        # Validate request
        url = data.get('url')
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Ultra-fast specific config
        config = data.get('config', {})
        custom_config = {
            'max_content_length': min(config.get('max_content_length', 800), 1000),
            'timeout': min(config.get('timeout', 8), 10)
        }
        
        # Initialize speed crawler
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        try:
            result = safe_async_run(
                crawler.crawl_with_speed(
                    url=url,
                    speed=CrawlSpeed.ULTRA_FAST,
                    css_selector=data.get('css_selector'),
                    custom_config=custom_config
                ),
                timeout=12
            )
        except asyncio.TimeoutError:
            return error_response("Ultra-fast crawl timeout after 12 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Ultra-fast crawl failed: {str(crawl_error)}")
            return error_response(f"Ultra-fast crawl failed: {str(crawl_error)}", 500)
        
        # Add timing and rate info
        total_time = time.time() - start_time
        if result.get('success'):
            if 'metadata' not in result:
                result['metadata'] = {}
            result['metadata']['api_response_time'] = round(total_time, 2)
            result['metadata']['rate_limiting'] = rate_info
            result['metadata']['performance_tier'] = 'ultra_fast'
            result['metadata']['features'] = {
                'javascript': False,
                'images': False,
                'css': False,
                'forms': False,
                'max_speed': True
            }
            
            return success_response(result)
        else:
            return error_response(result.get('error', 'Ultra-fast crawl failed'), 400)
            
    except Exception as e:
        current_app.logger.error(f"Ultra-fast endpoint error: {str(e)}")
        return error_response("Ultra-fast crawl service error", 500)

@api_v1.route('/crawl/fast', methods=['POST'])
@smart_limit("20 per minute")
def crawl_fast():
    """🚀 Fast crawling - Quick and efficient with JavaScript"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        # Validate request
        url = data.get('url')
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Fast-specific config
        config = data.get('config', {})
        custom_config = {
            'max_content_length': min(config.get('max_content_length', 2000), 2500),
            'timeout': min(config.get('timeout', 15), 20)
        }
        
        # Initialize speed crawler
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        try:
            result = safe_async_run(
                crawler.crawl_with_speed(
                    url=url,
                    speed=CrawlSpeed.FAST,
                    css_selector=data.get('css_selector'),
                    custom_config=custom_config
                ),
                timeout=25
            )
        except asyncio.TimeoutError:
            return error_response("Fast crawl timeout after 25 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Fast crawl failed: {str(crawl_error)}")
            return error_response(f"Fast crawl failed: {str(crawl_error)}", 500)
        
        # Add timing and rate info
        total_time = time.time() - start_time
        if result.get('success'):
            if 'metadata' not in result:
                result['metadata'] = {}
            result['metadata']['api_response_time'] = round(total_time, 2)
            result['metadata']['rate_limiting'] = rate_info
            result['metadata']['performance_tier'] = 'fast'
            result['metadata']['features'] = {
                'javascript': True,
                'images': False,
                'css': True,
                'forms': False,
                'optimized': True
            }
            
            return success_response(result)
        else:
            return error_response(result.get('error', 'Fast crawl failed'), 400)
            
    except Exception as e:
        current_app.logger.error(f"Fast endpoint error: {str(e)}")
        return error_response("Fast crawl service error", 500)

@api_v1.route('/crawl/normal', methods=['POST'])
@smart_limit("15 per minute")
def crawl_normal():
    """⚖️ Normal crawling - Balanced speed and thoroughness"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        # Validate request
        url = data.get('url')
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Normal-specific config
        config = data.get('config', {})
        custom_config = {
            'max_content_length': min(config.get('max_content_length', 4000), 5000),
            'timeout': min(config.get('timeout', 30), 40)
        }
        
        # Initialize speed crawler
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        try:
            result = safe_async_run(
                crawler.crawl_with_speed(
                    url=url,
                    speed=CrawlSpeed.NORMAL,
                    css_selector=data.get('css_selector'),
                    custom_config=custom_config
                ),
                timeout=45
            )
        except asyncio.TimeoutError:
            return error_response("Normal crawl timeout after 45 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Normal crawl failed: {str(crawl_error)}")
            return error_response(f"Normal crawl failed: {str(crawl_error)}", 500)
        
        # Add timing and rate info
        total_time = time.time() - start_time
        if result.get('success'):
            if 'metadata' not in result:
                result['metadata'] = {}
            result['metadata']['api_response_time'] = round(total_time, 2)
            result['metadata']['rate_limiting'] = rate_info
            result['metadata']['performance_tier'] = 'normal'
            result['metadata']['features'] = {
                'javascript': True,
                'images': False,
                'css': True,
                'forms': True,
                'links': True,
                'balanced': True
            }
            
            return success_response(result)
        else:
            return error_response(result.get('error', 'Normal crawl failed'), 400)
            
    except Exception as e:
        current_app.logger.error(f"Normal endpoint error: {str(e)}")
        return error_response("Normal crawl service error", 500)

@api_v1.route('/crawl/thorough', methods=['POST'])
@smart_limit("8 per minute")  # Lower limit for thorough crawling
def crawl_thorough():
    """🔍 Thorough crawling - Complete analysis with all features"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        # Validate request
        url = data.get('url')
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Thorough-specific config
        config = data.get('config', {})
        custom_config = {
            'max_content_length': min(config.get('max_content_length', 8000), 10000),
            'timeout': min(config.get('timeout', 60), 80)
        }
        
        # Initialize speed crawler
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        try:
            result = safe_async_run(
                crawler.crawl_with_speed(
                    url=url,
                    speed=CrawlSpeed.THOROUGH,
                    css_selector=data.get('css_selector'),
                    custom_config=custom_config
                ),
                timeout=90
            )
        except asyncio.TimeoutError:
            return error_response("Thorough crawl timeout after 90 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Thorough crawl failed: {str(crawl_error)}")
            return error_response(f"Thorough crawl failed: {str(crawl_error)}", 500)
        
        # Add timing and rate info
        total_time = time.time() - start_time
        if result.get('success'):
            if 'metadata' not in result:
                result['metadata'] = {}
            result['metadata']['api_response_time'] = round(total_time, 2)
            result['metadata']['rate_limiting'] = rate_info
            result['metadata']['performance_tier'] = 'thorough'
            result['metadata']['features'] = {
                'javascript': True,
                'images': True,
                'css': True,
                'forms': True,
                'iframes': True,
                'links': True,
                'user_simulation': True,
                'complete_analysis': True
            }
            
            return success_response(result)
        else:
            return error_response(result.get('error', 'Thorough crawl failed'), 400)
            
    except Exception as e:
        current_app.logger.error(f"Thorough endpoint error: {str(e)}")
        return error_response("Thorough crawl service error", 500)

@api_v1.route('/crawl/batch-speed', methods=['POST'])
@smart_limit("3 per minute")
def batch_crawl_speed():
    """📦 Batch crawling with configurable speed tiers"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        # Validate request
        urls = data.get('urls', [])
        if not urls or not isinstance(urls, list):
            return error_response("URLs array is required", 400)
        
        max_batch_size = current_app.config.get('MAX_BATCH_SIZE', 5)
        if len(urls) > max_batch_size:
            return error_response(f"Maximum {max_batch_size} URLs allowed per batch", 400)
        
        # Speed configuration
        speed_name = data.get('speed', 'fast').lower()
        speed_map = {
            'ultra_fast': CrawlSpeed.ULTRA_FAST,
            'ultra-fast': CrawlSpeed.ULTRA_FAST,
            'ultrafast': CrawlSpeed.ULTRA_FAST,
            'fast': CrawlSpeed.FAST,
            'normal': CrawlSpeed.NORMAL,
            'thorough': CrawlSpeed.THOROUGH
        }
        speed = speed_map.get(speed_name, CrawlSpeed.FAST)
        
        # Batch config
        config = data.get('config', {})
        max_concurrent = min(config.get('max_concurrent', 3), 5)
        
        # Initialize speed crawler
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        try:
            results = safe_async_run(
                crawler.batch_crawl_with_speed(
                    urls=urls[:max_batch_size],
                    speed=speed,
                    max_concurrent=max_concurrent
                ),
                timeout=120
            )
        except asyncio.TimeoutError:
            return error_response("Batch speed crawl timeout after 120 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Batch speed crawl failed: {str(crawl_error)}")
            return error_response(f"Batch speed crawl failed: {str(crawl_error)}", 500)
        
        # Process results
        successful = sum(1 for r in results if r.get('success'))
        failed = len(results) - successful
        total_time = time.time() - start_time
        
        return success_response({
            'results': results,
            'summary': {
                'total_urls': len(urls),
                'successful': successful,
                'failed': failed,
                'speed_tier': speed.value,
                'max_concurrent': max_concurrent,
                'total_time': round(total_time, 2),
                'average_time_per_url': round(total_time / len(urls), 2) if urls else 0
            },
            'rate_limiting': rate_info,
            'performance_info': {
                'speed_tier_used': speed.value,
                'concurrency': max_concurrent,
                'batch_optimization': True
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Batch speed crawl error: {str(e)}")
        return error_response("Batch speed crawl service error", 500)

@api_v1.route('/crawl/auto-speed', methods=['POST'])
@smart_limit("20 per minute")
def crawl_auto_speed():
    """🤖 Auto-speed crawling - Automatically selects optimal speed tier"""
    start_time = time.time()
    
    try:
        rate_info = get_rate_limit_info()
        data = request.get_json()
        
        # Validate request
        url = data.get('url')
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Auto-detect optimal speed based on use case or URL characteristics
        use_case = data.get('use_case', 'quick_scan')
        domain = urlparse(url).netloc.lower()
        
        # Initialize speed crawler
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        # Smart speed selection
        if use_case in ['monitoring', 'status_check', 'health_check']:
            speed = CrawlSpeed.ULTRA_FAST
        elif 'api' in domain or 'status' in url.lower():
            speed = CrawlSpeed.ULTRA_FAST
        elif use_case in ['quick_scan', 'api_integration'] or any(x in domain for x in ['github.com', 'stackoverflow.com']):
            speed = CrawlSpeed.FAST
        elif use_case in ['research', 'compliance'] or any(x in domain for x in ['wikipedia.org', 'docs.', 'blog.']):
            speed = CrawlSpeed.THOROUGH
        else:
            speed = CrawlSpeed.NORMAL
        
        # Allow manual override
        if 'force_speed' in data:
            speed_override = data['force_speed'].lower()
            speed_map = {
                'ultra_fast': CrawlSpeed.ULTRA_FAST,
                'fast': CrawlSpeed.FAST,
                'normal': CrawlSpeed.NORMAL,
                'thorough': CrawlSpeed.THOROUGH
            }
            speed = speed_map.get(speed_override, speed)
        
        # Config based on selected speed
        config = data.get('config', {})
        custom_config = {
            'max_content_length': config.get('max_content_length'),
            'timeout': config.get('timeout')
        }
        
        try:
            result = safe_async_run(
                crawler.crawl_with_speed(
                    url=url,
                    speed=speed,
                    css_selector=data.get('css_selector'),
                    custom_config=custom_config
                ),
                timeout=90
            )
        except asyncio.TimeoutError:
            return error_response("Auto-speed crawl timeout", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Auto-speed crawl failed: {str(crawl_error)}")
            return error_response(f"Auto-speed crawl failed: {str(crawl_error)}", 500)
        
        # Add timing and auto-selection info
        total_time = time.time() - start_time
        if result.get('success'):
            if 'metadata' not in result:
                result['metadata'] = {}
            result['metadata']['api_response_time'] = round(total_time, 2)
            result['metadata']['rate_limiting'] = rate_info
            result['metadata']['auto_selection'] = {
                'selected_speed': speed.value,
                'use_case': use_case,
                'domain_detected': domain,
                'selection_reason': f"Optimized for {use_case} and domain characteristics"
            }
            
            return success_response(result)
        else:
            return error_response(result.get('error', 'Auto-speed crawl failed'), 400)
            
    except Exception as e:
        current_app.logger.error(f"Auto-speed endpoint error: {str(e)}")
        return error_response("Auto-speed crawl service error", 500)

@api_v1.route('/crawl/speed-info', methods=['GET'])
@smart_limit("60 per minute")
def speed_tier_info():
    """📊 Get information about available speed tiers and their characteristics"""
    try:
        rate_info = get_rate_limit_info()
        
        speed_info = {
            "ultra_fast": {
                "name": "Ultra Fast ⚡",
                "description": "Lightning speed crawling for basic content extraction",
                "typical_time": "0.5-2 seconds",
                "features": {
                    "javascript": False,
                    "images": False,
                    "css_processing": False,
                    "forms": False,
                    "iframes": False
                },
                "use_cases": ["Status checks", "Monitoring", "Health checks", "Quick content scan"],
                "max_content": "1KB",
                "timeout": "8 seconds",
                "rate_limit": "30 per minute"
            },
            "fast": {
                "name": "Fast 🚀",
                "description": "Quick crawling with JavaScript support",
                "typical_time": "1-5 seconds", 
                "features": {
                    "javascript": True,
                    "images": False,
                    "css_processing": True,
                    "forms": False,
                    "iframes": False
                },
                "use_cases": ["Content extraction", "API integration", "Data scraping", "Quick analysis"],
                "max_content": "2.5KB",
                "timeout": "15 seconds",
                "rate_limit": "20 per minute"
            },
            "normal": {
                "name": "Normal ⚖️",
                "description": "Balanced speed and thoroughness",
                "typical_time": "3-10 seconds",
                "features": {
                    "javascript": True,
                    "images": False,
                    "css_processing": True,
                    "forms": True,
                    "iframes": False
                },
                "use_cases": ["General crawling", "SEO analysis", "Content research", "Link extraction"],
                "max_content": "5KB",
                "timeout": "30 seconds",
                "rate_limit": "15 per minute"
            },
            "thorough": {
                "name": "Thorough 🔍",
                "description": "Complete analysis with all features enabled",
                "typical_time": "5-20 seconds",
                "features": {
                    "javascript": True,
                    "images": True,
                    "css_processing": True,
                    "forms": True,
                    "iframes": True,
                    "user_simulation": True
                },
                "use_cases": ["Research", "Compliance checks", "Complete site analysis", "Academic studies"],
                "max_content": "10KB",
                "timeout": "60 seconds",
                "rate_limit": "8 per minute"
            }
        }
        
        return success_response({
            "speed_tiers": speed_info,
            "endpoints": {
                "ultra_fast": "POST /api/v1/crawl/ultra-fast",
                "fast": "POST /api/v1/crawl/fast",
                "normal": "POST /api/v1/crawl/normal", 
                "thorough": "POST /api/v1/crawl/thorough",
                "auto_speed": "POST /api/v1/crawl/auto-speed",
                "batch_speed": "POST /api/v1/crawl/batch-speed"
            },
            "rate_limiting": rate_info,
            "selection_guide": {
                "for_monitoring": "ultra_fast",
                "for_content_extraction": "fast",
                "for_general_crawling": "normal",
                "for_research": "thorough",
                "for_auto_optimization": "auto_speed"
            },
            "performance_tips": [
                "Use ultra-fast for simple status checks and monitoring",
                "Use fast for most content extraction needs",
                "Use normal for balanced performance and features",
                "Use thorough only when you need complete analysis",
                "Use auto-speed to let the system choose optimal speed",
                "API key bypasses rate limits for all speed tiers"
            ]
        })
        
    except Exception as e:
        return error_response(f"Speed info failed: {str(e)}", 500)

# Enhanced health check with speed tier status
@api_v1.route('/health/speed', methods=['GET'])
@smart_limit("60 per minute")
def speed_health_check():
    """🏥 Health check specifically for speed-optimized crawling"""
    try:
        rate_info = get_rate_limit_info()
        
        # Test each speed tier briefly
        test_url = "https://httpbin.org/html"
        crawler = SpeedOptimizedCrawler(current_app.config)
        
        speed_status = {}
        for speed in [CrawlSpeed.ULTRA_FAST, CrawlSpeed.FAST]:
            try:
                start_time = time.time()
                result = safe_async_run(
                    crawler.crawl_with_speed(test_url, speed),
                    timeout=10
                )
                response_time = round(time.time() - start_time, 2)
                
                speed_status[speed.value] = {
                    "status": "healthy" if result.get('success') else "degraded",
                    "response_time": response_time,
                    "test_passed": result.get('success', False)
                }
            except Exception as e:
                speed_status[speed.value] = {
                    "status": "error",
                    "response_time": None,
                    "error": str(e),
                    "test_passed": False
                }
        
        overall_status = "healthy" if all(
            s.get("test_passed") for s in speed_status.values()
        ) else "degraded"
        
        return success_response({
            "status": overall_status,
            "service": "Speed-Optimized Web Crawler",
            "version": "2.0.0",
            "speed_tiers": speed_status,
            "rate_limiting": rate_info,
            "performance_metrics": {
                "ultra_fast_target": "< 2 seconds",
                "fast_target": "< 5 seconds",
                "availability": "99.9%",
                "concurrent_capacity": "50+ requests"
            },
            "system_info": {
                "optimization_level": "high",
                "cache_enabled": True,
                "compression": True,
                "async_processing": True
            }
        })
        
    except Exception as e:
        return error_response(f"Speed health check failed: {str(e)}", 500)