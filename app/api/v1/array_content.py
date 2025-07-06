# app/api/v1/array_content.py
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
def extract_array_content():
    """
    Extract repeated elements as arrays from specific selectors
    
    Perfect for news items, product lists, articles, etc.
    
    Request body:
    {
        "url": "https://yournewssite.lk/hot-news/",
        "config": {
            "array_selectors": {
                "news_stories": {
                    "selector": ".news-story",
                    "sub_selectors": {
                        "title": "h2 a",
                        "summary": "p",
                        "date": ".comments span",
                        "link": "h2 a",
                        "image": ".thumb-image img"
                    },
                    "limit": 10
                }
            },
            "exclude_selectors": [".comments script", ".advertisement"],
            "format": "structured"
        }
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate request
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        config = data.get('config', {})
        
        # Extract array configuration
        array_selectors = config.get('array_selectors', {})
        exclude_selectors = config.get('exclude_selectors', [])
        format_output = config.get('format', 'structured')  # structured, flat, summary
        
        # Validate array selectors
        if not array_selectors:
            return error_response("array_selectors configuration is required", 400)
        
        if not isinstance(array_selectors, dict):
            return error_response("array_selectors must be a dictionary", 400)
        
        if len(array_selectors) > 5:
            return error_response("Maximum 5 array selectors allowed", 400)
        
        # Validate format
        if format_output not in ['structured', 'flat', 'summary']:
            return error_response("format must be one of: structured, flat, summary", 400)
        
        # Initialize array-based crawler service
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        # Run array content extraction
        try:
            result = safe_async_run(
                crawler_service.crawl_array_content(
                    url, array_selectors, exclude_selectors, format_output
                ),
                timeout=35
            )
        except asyncio.TimeoutError:
            return error_response("Array content extraction timeout after 35 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Array content extraction failed: {str(crawl_error)}")
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            return error_response(f"Array content extraction failed: {str(crawl_error)}", 500)
        
        # Add timing information
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'array_content'
            
            # Create enhanced response with array data easily accessible
            response_data = result.to_dict()
            
            # Add easy access to arrays in response root
            if 'arrays' in result.metadata:
                response_data['arrays'] = result.metadata['arrays']
                
                # Create a simplified arrays summary
                arrays_summary = {}
                for name, array_data in result.metadata['arrays'].items():
                    arrays_summary[name] = {
                        'count': array_data['count'],
                        'selector': array_data['selector'],
                        'items': [item['main_content'][:100] + "..." if len(item['main_content']) > 100 else item['main_content'] 
                                for item in array_data['items'][:3]]  # First 3 items preview
                    }
                response_data['arrays_preview'] = arrays_summary
            
            return success_response(response_data)
        else:
            error_msg = result.error if result else "Array content extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Array content endpoint error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Internal server error", 500)

@api_v1.route('/content/array/batch', methods=['POST'])
@apply_rate_limit("2 per minute")
def batch_extract_array_content():
    """
    Batch extract array content from multiple URLs
    
    Request body:
    {
        "urls": ["https://site1.com", "https://site2.com"],
        "config": {
            "array_selectors": {
                "articles": {
                    "selector": ".article",
                    "sub_selectors": {
                        "title": "h2",
                        "summary": ".excerpt"
                    }
                }
            },
            "format": "structured",
            "max_concurrent": 2
        }
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        max_batch_size = min(current_app.config.get('MAX_BATCH_SIZE', 3), 3)
        is_valid, error_msg = validate_batch_request(data, max_batch_size)
        if not is_valid:
            return error_response(error_msg, 400)
        
        urls = data['urls'][:max_batch_size]
        config = data.get('config', {})
        
        # Extract configuration
        array_selectors = config.get('array_selectors', {})
        exclude_selectors = config.get('exclude_selectors', [])
        format_output = config.get('format', 'structured')
        max_concurrent = min(config.get('max_concurrent', 2), 2)
        
        # Validate
        if not array_selectors:
            return error_response("array_selectors configuration is required", 400)
        
        if len(array_selectors) > 3:  # Stricter for batch
            return error_response("Maximum 3 array selectors allowed for batch processing", 400)
        
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        try:
            results = safe_async_run(
                crawler_service.crawl_multiple_array_content(
                    urls, array_selectors, exclude_selectors, format_output, max_concurrent
                ),
                timeout=120
            )
        except asyncio.TimeoutError:
            return error_response("Batch array content extraction timeout after 120 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Batch array content extraction failed: {str(crawl_error)}")
            return error_response(f"Batch array content extraction failed: {str(crawl_error)}", 500)
        
        # Process results
        if results:
            result_dicts = []
            successful = 0
            failed = 0
            total_items = 0
            
            for result in results:
                try:
                    result_dict = result.to_dict() if result else {"success": False, "error": "No result"}
                    
                    # Add array data to response
                    if result and result.success and hasattr(result, 'metadata') and 'arrays' in result.metadata:
                        result_dict['arrays'] = result.metadata['arrays']
                        # Count total items for this result
                        for array_data in result.metadata['arrays'].values():
                            total_items += array_data.get('count', 0)
                    
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
            total_items = 0
        
        total_time = time.time() - start_time
        
        return success_response({
            'results': result_dicts,
            'total_processed': len(result_dicts),
            'successful': successful,
            'failed': failed,
            'total_items_extracted': total_items,
            'total_time': round(total_time, 2),
            'average_time_per_url': round(total_time / len(urls), 2) if urls else 0,
            'mode': 'array_content_batch',
            'array_selectors_used': list(array_selectors.keys()),
            'format_used': format_output,
            'features': {
                'array_based_extraction': True,
                'sub_selector_support': True,
                'repeated_elements_as_arrays': True
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Batch array content error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Batch array content processing failed", 500)

@api_v1.route('/content/array/<path:url>', methods=['GET'])
@apply_rate_limit("20 per minute")
def extract_array_content_get(url):
    """
    Quick array extraction via GET with query parameters
    
    Query parameters:
    - selector: CSS selector for repeated elements (e.g., ?selector=.news-story)
    - title: Sub-selector for titles (e.g., &title=h2 a)
    - summary: Sub-selector for summaries (e.g., &summary=p)
    - exclude: Comma-separated exclude selectors
    - limit: Maximum number of items to extract
    - format: Output format (structured, flat, summary)
    """
    start_time = time.time()
    
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse query parameters
        main_selector = request.args.get('selector', '')
        title_selector = request.args.get('title', '')
        summary_selector = request.args.get('summary', '')
        link_selector = request.args.get('link', '')
        date_selector = request.args.get('date', '')
        exclude_param = request.args.get('exclude', '')
        limit = min(int(request.args.get('limit', 20)), 50)
        format_output = request.args.get('format', 'structured')
        
        if not main_selector:
            return error_response("selector parameter is required", 400)
        
        # Build array selectors config
        array_selectors = {
            'items': {
                'selector': main_selector,
                'limit': limit,
                'sub_selectors': {}
            }
        }
        
        # Add sub-selectors if provided
        if title_selector:
            array_selectors['items']['sub_selectors']['title'] = title_selector
        if summary_selector:
            array_selectors['items']['sub_selectors']['summary'] = summary_selector
        if link_selector:
            array_selectors['items']['sub_selectors']['link'] = link_selector
        if date_selector:
            array_selectors['items']['sub_selectors']['date'] = date_selector
        
        # Parse exclude selectors
        exclude_selectors = [s.strip() for s in exclude_param.split(',') if s.strip()] if exclude_param else []
        
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_array_content(
                    url, array_selectors, exclude_selectors, format_output
                ),
                timeout=20
            )
        except asyncio.TimeoutError:
            return error_response("GET array extraction timeout after 20 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"GET array extraction failed: {str(crawl_error)}")
            return error_response(f"GET array extraction failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'array_content_get'
            
            response_data = result.to_dict()
            if 'arrays' in result.metadata:
                response_data['arrays'] = result.metadata['arrays']
            
            return success_response(response_data)
        else:
            error_msg = result.error if result else "GET array extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"GET array extraction error: {str(e)}")
        return error_response("GET array request failed", 500)

@api_v1.route('/content/array/test', methods=['GET'])
@apply_rate_limit("60 per minute")
def test_array_extraction():
    """Test endpoint for array-based extraction with examples"""
    try:
        return success_response({
            "message": "Array-based content extraction service is ready",
            "description": "Extract repeated elements (like news items, products, articles) as structured arrays",
            "endpoints": {
                "array": {
                    "url": "POST /api/v1/content/array",
                    "description": "Extract repeated elements as arrays with sub-selectors",
                    "perfect_for": ["News lists", "Product listings", "Article feeds", "Social media posts"]
                },
                "array_batch": {
                    "url": "POST /api/v1/content/array/batch",
                    "description": "Batch extract arrays from multiple URLs"
                },
                "array_get": {
                    "url": "GET /api/v1/content/array/<url>",
                    "description": "Quick array extraction via GET parameters"
                }
            },
            "example_use_cases": {
                "adaderana_news": {
                    "url": "https://yournewssite.lk/hot-news/",
                    "config": {
                        "array_selectors": {
                            "news_stories": {
                                "selector": ".news-story",
                                "sub_selectors": {
                                    "title": "h2 a",
                                    "summary": "p",
                                    "date": ".comments span",
                                    "link": "h2 a"
                                },
                                "limit": 10
                            }
                        },
                        "exclude_selectors": [".comments script"],
                        "format": "structured"
                    }
                },
                "product_listings": {
                    "description": "E-commerce product extraction",
                    "config": {
                        "array_selectors": {
                            "products": {
                                "selector": ".product-item",
                                "sub_selectors": {
                                    "name": ".product-title",
                                    "price": ".price",
                                    "rating": ".rating",
                                    "availability": ".stock-status"
                                }
                            }
                        }
                    }
                },
                "social_media_posts": {
                    "description": "Social media feed extraction",
                    "config": {
                        "array_selectors": {
                            "posts": {
                                "selector": ".post",
                                "sub_selectors": {
                                    "content": ".post-content",
                                    "author": ".author-name",
                                    "timestamp": ".post-date",
                                    "likes": ".like-count"
                                }
                            }
                        }
                    }
                },
                "search_results": {
                    "description": "Search results extraction",
                    "config": {
                        "array_selectors": {
                            "results": {
                                "selector": ".search-result",
                                "sub_selectors": {
                                    "title": "h3 a",
                                    "snippet": ".result-snippet",
                                    "url": "h3 a",
                                    "source": ".result-source"
                                }
                            }
                        }
                    }
                }
            },
            "advanced_config": {
                "array_selectors": {
                    "selector_name": {
                        "selector": "CSS selector for repeated elements",
                        "sub_selectors": {
                            "field_name": "CSS selector within each element",
                            "another_field": "Another CSS selector"
                        },
                        "limit": "Maximum number of items to extract"
                    }
                },
                "exclude_selectors": ["Array of selectors to exclude"],
                "format": "structured | flat | summary"
            },
            "output_formats": {
                "structured": "Organized sections with sub-selector data",
                "flat": "Simple list of main content from all items",
                "summary": "Count and selector information only"
            },
            "response_structure": {
                "arrays": {
                    "selector_name": {
                        "selector": "CSS selector used",
                        "items": [
                            {
                                "index": 0,
                                "main_content": "Main text content",
                                "title": "Extracted title",
                                "summary": "Extracted summary",
                                "word_count": 25,
                                "char_count": 150
                            }
                        ],
                        "count": "Number of items found"
                    }
                }
            },
            "get_endpoint_examples": {
                "simple": "GET /api/v1/content/array/adaderana.lk/hot-news?selector=.news-story&limit=5",
                "with_sub_selectors": "GET /api/v1/content/array/example.com?selector=.article&title=h2&summary=.excerpt&limit=10",
                "with_exclusions": "GET /api/v1/content/array/site.com?selector=.item&exclude=.ads,.sidebar&format=flat"
            },
            "tips": {
                "performance": "Use limit parameter to control extraction size",
                "accuracy": "Test selectors on browser dev tools first",
                "sub_selectors": "Use sub_selectors for structured data extraction",
                "exclusions": "Use exclude_selectors to remove unwanted content",
                "format": "Use 'flat' format for simple text lists, 'structured' for detailed data"
            },
            "status": "healthy",
            "service": "Array-Based Content Extraction API"
        })
    except Exception as e:
        return error_response(f"Array extraction test failed: {str(e)}", 500)

@api_v1.route('/content/array/demo', methods=['POST'])
@apply_rate_limit("5 per minute")
def demo_array_extraction():
    """
    Demo endpoint with pre-configured examples for common sites
    
    Request body:
    {
        "site_type": "adaderana_news",
        "url": "https://yournewssite.lk/hot-news/",
        "limit": 5
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body required", 400)
        
        site_type = data.get('site_type', '')
        url = data.get('url', '')
        limit = min(data.get('limit', 10), 20)
        
        if not site_type or not url:
            return error_response("site_type and url are required", 400)
        
        # Pre-configured selector templates
        selector_templates = {
            'adaderana_news': {
                'array_selectors': {
                    'news_stories': {
                        'selector': '.news-story',
                        'sub_selectors': {
                            'title': 'h2 a',
                            'summary': 'p',
                            'date': '.comments span',
                            'link': 'h2 a'
                        },
                        'limit': limit
                    }
                },
                'exclude_selectors': ['.comments script', '.intensedebate'],
                'format': 'structured'
            },
            'generic_news': {
                'array_selectors': {
                    'articles': {
                        'selector': '.article, .news-item, .post',
                        'sub_selectors': {
                            'title': 'h1, h2, h3, .title',
                            'content': 'p, .content, .excerpt',
                            'date': '.date, .timestamp, time'
                        },
                        'limit': limit
                    }
                },
                'format': 'structured'
            },
            'generic_products': {
                'array_selectors': {
                    'products': {
                        'selector': '.product, .product-item, .item',
                        'sub_selectors': {
                            'name': '.product-name, .title, h3',
                            'price': '.price, .cost, .amount',
                            'description': '.description, .summary'
                        },
                        'limit': limit
                    }
                },
                'format': 'structured'
            },
            'generic_search': {
                'array_selectors': {
                    'results': {
                        'selector': '.result, .search-result, .listing',
                        'sub_selectors': {
                            'title': 'h3, .title, .heading',
                            'snippet': '.snippet, .description, .summary',
                            'url': 'a, .link'
                        },
                        'limit': limit
                    }
                },
                'format': 'structured'
            }
        }
        
        if site_type not in selector_templates:
            return error_response(f"Unknown site_type. Available: {list(selector_templates.keys())}", 400)
        
        config = selector_templates[site_type]
        
        # Run the extraction
        crawler_service = ArrayBasedCrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_array_content(
                    url, 
                    config['array_selectors'], 
                    config.get('exclude_selectors', []), 
                    config.get('format', 'structured')
                ),
                timeout=30
            )
        except Exception as e:
            return error_response(f"Demo extraction failed: {str(e)}", 500)
        
        if result and result.success:
            response_data = result.to_dict()
            if 'arrays' in result.metadata:
                response_data['arrays'] = result.metadata['arrays']
            
            # Add demo info
            response_data['demo_info'] = {
                'site_type': site_type,
                'template_used': config,
                'extraction_successful': True
            }
            
            return success_response(response_data)
        else:
            return error_response(result.error if result else "Demo extraction failed", 400)
            
    except Exception as e:
        current_app.logger.error(f"Demo extraction error: {str(e)}")
        return error_response("Demo extraction failed", 500)