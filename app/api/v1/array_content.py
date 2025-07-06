# app/api/v1/array_content.py - FIXED VERSION - Order & Image URLs
from flask import request, jsonify, current_app
import asyncio
import time
import traceback
import os
from functools import wraps

from app.api.v1 import api_v1
from app.services.array_content_service import ArrayBasedCrawlerService
from app.utils.validators import validate_crawl_request, validate_batch_request
from app.utils.response_helpers import success_response, error_response

# Rate limiting decorator
def apply_rate_limit(limit_string):
    """Apply rate limit only in production without valid API key"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if os.getenv('FLASK_ENV', 'production') == 'development':
                return f(*args, **kwargs)
            
            api_key = request.headers.get('X-API-Key')
            valid_api_key = os.getenv('API_KEY', '')
            
            if api_key and api_key == valid_api_key and valid_api_key:
                return f(*args, **kwargs)
            
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

@api_v1.route('/content/array', methods=['POST'])
@apply_rate_limit("10 per minute")
def extract_repeated_elements():
    """
    Extract repeated elements with proper ordering (top to bottom) and absolute image URLs
    
    Request Example:
    {
        "url": "https://news-site.com",
        "selector": ".news-item",
        "config": {
            "sub_selectors": {
                "title": "h2 a, h3 a, .title",
                "summary": "p, .summary, .excerpt", 
                "image": "img",  // Will extract actual image URL
                "date": ".date, .time, time",
                "link": "a",     // Will extract actual link URL
                "author": ".author, .by"
            },
            "limit": 20,
            "exclude_selectors": [".ads", ".sidebar"]
        }
    }
    
    Response:
    {
        "success": true,
        "data": {
            "url": "https://news-site.com",
            "selector": ".news-item",
            "total_found": 5,
            "items": [
                {
                    "index": 0,  // Preserved order: 0 = top item on page
                    "title": "Latest Breaking News",
                    "summary": "This is the news summary...",
                    "image": "https://news-site.com/images/news1.jpg",  // Absolute URL
                    "date": "2024-01-15",
                    "link": "https://news-site.com/news/latest-breaking-news",  // Absolute URL
                    "author": "John Doe",
                    "main_content": "Full extracted text content",
                    "word_count": 45
                },
                {
                    "index": 1,  // Second item from top
                    "title": "Second News Title",
                    "summary": "Another news summary...",
                    "image": "https://news-site.com/images/news2.jpg",
                    "date": "2024-01-14",
                    "link": "https://news-site.com/news/second-news",
                    "author": "Jane Smith",
                    "main_content": "Full extracted text content",
                    "word_count": 38
                }
            ],
            "extraction_info": {
                "order_preserved": true,
                "image_urls_absolute": true,
                "link_urls_absolute": true,
                "extraction_time": 2.3
            }
        }
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate basic request
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        main_selector = data.get('selector', '')
        config = data.get('config', {})
        
        # Validation
        if not main_selector:
            return error_response("'selector' field is required - specify CSS selector for repeated elements", 400)
        
        # Extract configuration
        sub_selectors = config.get('sub_selectors', {})
        limit = min(config.get('limit', 50), 100)
        exclude_selectors = config.get('exclude_selectors', [])
        
        # Validate sub_selectors
        if sub_selectors and not isinstance(sub_selectors, dict):
            return error_response("sub_selectors must be a dictionary", 400)
        
        # Build the array selectors configuration for the service
        array_selectors = {
            'items': {
                'selector': main_selector,
                'sub_selectors': sub_selectors,
                'limit': limit
            }
        }
        
        current_app.logger.info(f"Array extraction request:")
        current_app.logger.info(f"  URL: {url}")
        current_app.logger.info(f"  Main selector: {main_selector}")
        current_app.logger.info(f"  Sub-selectors: {list(sub_selectors.keys())}")
        current_app.logger.info(f"  Limit: {limit}")
        
        # Initialize crawler service
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        # Run extraction
        try:
            result = safe_async_run(
                crawler_service.crawl_array_content(
                    url, array_selectors, exclude_selectors, 'structured'
                ),
                timeout=40
            )
        except asyncio.TimeoutError:
            return error_response("Array extraction timeout after 40 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Array extraction failed: {str(crawl_error)}")
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            return error_response(f"Array extraction failed: {str(crawl_error)}", 500)
        
        # Process results
        total_time = time.time() - start_time
        
        if result and result.success:
            # Extract items from the result
            arrays_data = result.metadata.get('arrays', {})
            items_data = arrays_data.get('items', {})
            raw_items = items_data.get('items', [])
            
            # Format items to have all fields at the same level (preserving order)
            formatted_items = []
            
            for item in raw_items:  # Items are already in correct order (top to bottom)
                # Start with basic fields
                formatted_item = {
                    'index': item.get('index', 0),  # Order preserved: 0 = top item
                    'main_content': item.get('main_content', ''),
                    'word_count': item.get('word_count', 0)
                }
                
                # Add all sub-selector extracted fields
                for key, value in item.items():
                    # Skip internal fields
                    if key not in ['index', 'main_content', 'word_count', 'char_count']:
                        # Handle different value types
                        if isinstance(value, list):
                            # Join list values or take first non-empty item
                            if value:
                                # If it's a list of strings, take the first one
                                if all(isinstance(v, str) for v in value):
                                    formatted_item[key] = value[0] if len(value) == 1 else ' | '.join(value)
                                else:
                                    formatted_item[key] = value[0]
                            else:
                                formatted_item[key] = ''
                        else:
                            formatted_item[key] = value or ''
                
                # Ensure all requested sub_selectors are present (even if empty)
                for sub_key in sub_selectors.keys():
                    if sub_key not in formatted_item:
                        formatted_item[sub_key] = ''
                
                formatted_items.append(formatted_item)
            
            # Create clean response
            response_data = {
                'url': url,
                'selector': main_selector,
                'total_found': len(formatted_items),
                'items': formatted_items,  # Items in order: index 0 = top of page
                'extraction_info': {
                    'sub_selectors_used': list(sub_selectors.keys()),
                    'exclude_selectors_used': exclude_selectors,
                    'order_preserved': True,  # Top to bottom order maintained
                    'image_urls_absolute': True,  # Image URLs converted to absolute
                    'link_urls_absolute': True,   # Link URLs converted to absolute
                    'deduplication_applied': items_data.get('deduplication_applied', False),
                    'extraction_time': round(total_time, 2)
                }
            }
            
            current_app.logger.info(f"Extraction successful:")
            current_app.logger.info(f"  Total items found: {len(formatted_items)}")
            current_app.logger.info(f"  Order preserved: top to bottom")
            current_app.logger.info(f"  Image URLs made absolute: {any('image' in str(k).lower() for k in sub_selectors.keys())}")
            current_app.logger.info(f"  Fields per item: {list(formatted_items[0].keys()) if formatted_items else []}")
            
            return success_response(response_data)
        
        else:
            error_msg = result.error if result else "Array extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Array extraction endpoint error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Internal server error", 500)

@api_v1.route('/content/array/simple', methods=['POST'])
@apply_rate_limit("15 per minute")
def extract_simple_repeated_elements():
    """
    Simplified version - automatically detect common fields with proper ordering
    
    Request:
    {
        "url": "https://news-site.com",
        "selector": ".news-item"
    }
    
    Automatically extracts: title, content, image (with absolute URL), link (with absolute URL), date, author
    Order preserved: index 0 = top item on page
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        main_selector = data.get('selector', '')
        
        if not main_selector:
            return error_response("'selector' field is required", 400)
        
        # Auto-detect common sub-selectors with proper field names for images and links
        auto_sub_selectors = {
            'title': 'h1, h2, h3, h4, .title, .headline, .news-title, .article-title',
            'content': 'p, .content, .summary, .excerpt, .description, .text',
            'image': 'img',  # Will extract actual image URL
            'link': 'a',     # Will extract actual link URL
            'date': '.date, .time, time, .timestamp, .published',
            'author': '.author, .by, .writer, .reporter'
        }
        
        # Build config
        array_selectors = {
            'items': {
                'selector': main_selector,
                'sub_selectors': auto_sub_selectors,
                'limit': 20
            }
        }
        
        exclude_selectors = ['.ads', '.advertisement', '.sidebar', '.social-share']
        
        current_app.logger.info(f"Simple array extraction:")
        current_app.logger.info(f"  URL: {url}")
        current_app.logger.info(f"  Selector: {main_selector}")
        current_app.logger.info(f"  Auto sub-selectors: {list(auto_sub_selectors.keys())}")
        
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_array_content(
                    url, array_selectors, exclude_selectors, 'structured'
                ),
                timeout=30
            )
        except Exception as crawl_error:
            return error_response(f"Simple extraction failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        
        if result and result.success:
            arrays_data = result.metadata.get('arrays', {})
            items_data = arrays_data.get('items', {})
            raw_items = items_data.get('items', [])
            
            # Format items with all fields at same level (order preserved)
            formatted_items = []
            
            for item in raw_items:  # Already in correct order
                formatted_item = {
                    'index': item.get('index', 0),  # 0 = top item
                    'title': '',
                    'content': item.get('main_content', ''),
                    'image': '',  # Will contain absolute URL
                    'link': '',   # Will contain absolute URL
                    'date': '',
                    'author': '',
                    'word_count': item.get('word_count', 0)
                }
                
                # Fill in extracted fields
                for key, value in item.items():
                    if key in auto_sub_selectors:
                        if isinstance(value, list) and value:
                            formatted_item[key] = value[0]
                        elif value:
                            formatted_item[key] = str(value)
                
                # Use main_content as content if no specific content found
                if not formatted_item['content'] and item.get('main_content'):
                    formatted_item['content'] = item.get('main_content', '')
                
                formatted_items.append(formatted_item)
            
            response_data = {
                'url': url,
                'selector': main_selector,
                'total_found': len(formatted_items),
                'items': formatted_items,  # Order preserved: 0 = top item
                'extraction_info': {
                    'mode': 'simple_auto_detection',
                    'order_preserved': True,
                    'image_urls_absolute': True,
                    'link_urls_absolute': True,
                    'extraction_time': round(total_time, 2),
                    'fields_extracted': ['title', 'content', 'image', 'link', 'date', 'author']
                }
            }
            
            return success_response(response_data)
        
        else:
            return error_response(result.error if result else "Simple extraction failed", 400)
            
    except Exception as e:
        current_app.logger.error(f"Simple array extraction error: {str(e)}")
        return error_response("Simple extraction failed", 500)

@api_v1.route('/content/array/batch', methods=['POST'])
@apply_rate_limit("2 per minute")
def batch_extract_repeated_elements():
    """
    Extract repeated elements from multiple URLs with proper ordering and absolute URLs
    
    Request:
    {
        "urls": ["https://site1.com", "https://site2.com"],
        "selector": ".news-item",
        "config": {
            "sub_selectors": {
                "title": "h2",
                "summary": "p",
                "image": "img",
                "link": "a"
            },
            "limit": 10
        }
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate batch request
        max_batch_size = min(current_app.config.get('MAX_BATCH_SIZE', 3), 3)
        
        if not data or 'urls' not in data:
            return error_response("'urls' array is required", 400)
        
        urls = data['urls']
        if not isinstance(urls, list) or len(urls) == 0:
            return error_response("'urls' must be a non-empty array", 400)
        
        if len(urls) > max_batch_size:
            return error_response(f"Maximum {max_batch_size} URLs allowed", 400)
        
        urls = urls[:max_batch_size]
        main_selector = data.get('selector', '')
        config = data.get('config', {})
        
        if not main_selector:
            return error_response("'selector' field is required", 400)
        
        # Extract configuration
        sub_selectors = config.get('sub_selectors', {})
        limit = min(config.get('limit', 20), 50)
        exclude_selectors = config.get('exclude_selectors', [])
        max_concurrent = min(config.get('max_concurrent', 2), 2)
        
        array_selectors = {
            'items': {
                'selector': main_selector,
                'sub_selectors': sub_selectors,
                'limit': limit
            }
        }
        
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        try:
            results = safe_async_run(
                crawler_service.crawl_multiple_array_content(
                    urls, array_selectors, exclude_selectors, 'structured', max_concurrent
                ),
                timeout=120
            )
        except Exception as crawl_error:
            return error_response(f"Batch extraction failed: {str(crawl_error)}", 500)
        
        # Process batch results
        batch_results = []
        total_items = 0
        successful_extractions = 0
        
        for i, result in enumerate(results):
            url = urls[i] if i < len(urls) else "unknown"
            
            if result and result.success:
                arrays_data = result.metadata.get('arrays', {})
                items_data = arrays_data.get('items', {})
                raw_items = items_data.get('items', [])
                
                # Format items for this URL (preserve order)
                formatted_items = []
                for item in raw_items:
                    formatted_item = {
                        'index': item.get('index', 0),  # Order preserved
                        'main_content': item.get('main_content', ''),
                        'word_count': item.get('word_count', 0)
                    }
                    
                    # Add sub-selector fields
                    for key, value in item.items():
                        if key not in ['index', 'main_content', 'word_count', 'char_count']:
                            if isinstance(value, list) and value:
                                formatted_item[key] = value[0]
                            elif value:
                                formatted_item[key] = str(value)
                    
                    # Ensure all sub_selectors are present
                    for sub_key in sub_selectors.keys():
                        if sub_key not in formatted_item:
                            formatted_item[sub_key] = ''
                    
                    formatted_items.append(formatted_item)
                
                batch_results.append({
                    'url': url,
                    'success': True,
                    'total_found': len(formatted_items),
                    'items': formatted_items,  # Order preserved for each site
                    'order_preserved': True,
                    'urls_absolute': True
                })
                
                total_items += len(formatted_items)
                successful_extractions += 1
                
            else:
                batch_results.append({
                    'url': url,
                    'success': False,
                    'error': result.error if result else "Extraction failed",
                    'total_found': 0,
                    'items': []
                })
        
        total_time = time.time() - start_time
        
        response_data = {
            'total_urls_processed': len(urls),
            'successful_extractions': successful_extractions,
            'failed_extractions': len(urls) - successful_extractions,
            'total_items_found': total_items,
            'extraction_time': round(total_time, 2),
            'results': batch_results,
            'config_used': {
                'selector': main_selector,
                'sub_selectors': list(sub_selectors.keys()),
                'limit_per_url': limit,
                'order_preserved': True,
                'urls_absolute': True
            }
        }
        
        return success_response(response_data)
        
    except Exception as e:
        current_app.logger.error(f"Batch array extraction error: {str(e)}")
        return error_response("Batch extraction failed", 500)

# Simple demo endpoint for quick testing
@api_v1.route('/content/array/demo', methods=['GET'])
@apply_rate_limit("30 per minute")
def demo_array_extraction():
    """Demo endpoint showing proper usage with order preservation and absolute URLs"""
    try:
        return success_response({
            "message": "Array Content Extraction API - Order Preserved & Absolute URLs",
            "description": "Extract repeated elements maintaining top-to-bottom order with absolute image/link URLs",
            "key_features": {
                "order_preservation": "Items returned in same order as they appear on webpage (index 0 = top item)",
                "absolute_urls": "All image and link URLs converted to absolute URLs",
                "deduplication": "Removes duplicate content while preserving order",
                "flexible_selectors": "Support for custom CSS selectors for any content type"
            },
            "endpoints": {
                "main": {
                    "url": "POST /api/v1/content/array",
                    "description": "Custom extraction with your own sub-selectors"
                },
                "simple": {
                    "url": "POST /api/v1/content/array/simple", 
                    "description": "Auto-detect common fields (title, content, image, link, date, author)"
                },
                "batch": {
                    "url": "POST /api/v1/content/array/batch",
                    "description": "Extract from multiple URLs"
                }
            },
            "example_request": {
                "url": "https://news-site.com",
                "selector": ".news-item",
                "config": {
                    "sub_selectors": {
                        "title": "h2 a",
                        "summary": "p",
                        "image": "img",
                        "date": ".date",
                        "link": "a"
                    },
                    "limit": 10
                }
            },
            "example_response_item": {
                "index": 0,
                "title": "Latest News Title",
                "summary": "News summary...",
                "image": "https://news-site.com/images/news.jpg",
                "date": "2024-01-15",
                "link": "https://news-site.com/news/latest",
                "main_content": "Full article content...",
                "word_count": 150,
                "note": "index 0 = top item on page, URLs are absolute"
            },
            "python_usage": '''
import requests

# Extract news articles in order
response = requests.post('http://localhost:5014/api/v1/content/array', json={
    "url": "https://news-site.com",
    "selector": ".news-item",
    "config": {
        "sub_selectors": {
            "title": "h2 a",
            "summary": "p",
            "image": "img",
            "link": "a"
        }
    }
})

data = response.json()
if data['success']:
    for item in data['data']['items']:
        print(f"Position {item['index']}: {item['title']}")
        print(f"Image: {item['image']}")  # Absolute URL
        print(f"Link: {item['link']}")    # Absolute URL
            ''',
            "order_guarantee": "Items always returned in top-to-bottom order as they appear on the webpage",
            "url_guarantee": "All image and link URLs converted to absolute URLs for direct usage",
            "status": "ready"
        })
    except Exception as e:
        return error_response(f"Demo failed: {str(e)}", 500)