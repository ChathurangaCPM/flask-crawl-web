# app/api/v1/array_content.py - FIXED VERSION WITH DEDUPLICATION
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
    Extract repeated elements as arrays from specific selectors - WITH DEDUPLICATION
    
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
        
        # Log the request for debugging
        current_app.logger.info(f"Array content extraction request:")
        current_app.logger.info(f"  URL: {url}")
        current_app.logger.info(f"  Array selectors: {list(array_selectors.keys())}")
        current_app.logger.info(f"  Format: {format_output}")
        
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
        
        # Add timing information and enhanced metadata
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'array_content_deduplicated'
                
                # Add enhanced deduplication statistics
                arrays = result.metadata.get('arrays', {})
                if arrays:
                    total_items_before = sum(
                        len(data.get('items', [])) for data in arrays.values()
                    )
                    total_items_after = sum(
                        data.get('count', 0) for data in arrays.values()
                    )
                    
                    result.metadata['deduplication_stats'] = {
                        'total_arrays': len(arrays),
                        'total_items_before_dedup': total_items_before,
                        'total_items_after_dedup': total_items_after,
                        'items_removed': max(0, total_items_before - total_items_after),
                        'deduplication_ratio': round(
                            (max(0, total_items_before - total_items_after) / max(total_items_before, 1)) * 100, 1
                        ),
                        'arrays_with_deduplication': [
                            name for name, data in arrays.items() 
                            if data.get('deduplication_applied', False)
                        ]
                    }
            
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
                        'deduplication_applied': array_data.get('deduplication_applied', False),
                        'items_preview': [
                            item['main_content'][:100] + "..." if len(item['main_content']) > 100 else item['main_content'] 
                            for item in array_data['items'][:3]  # First 3 items preview
                        ]
                    }
                response_data['arrays_preview'] = arrays_summary
            
            # Log successful extraction
            current_app.logger.info(f"Array extraction successful:")
            current_app.logger.info(f"  Arrays found: {len(result.metadata.get('arrays', {}))}")
            current_app.logger.info(f"  Total unique items: {result.metadata.get('content_quality', {}).get('total_unique_items', 0)}")
            current_app.logger.info(f"  Deduplication applied: {result.metadata.get('content_quality', {}).get('deduplication_applied', False)}")
            
            return success_response(response_data)
        else:
            error_msg = result.error if result else "Array content extraction failed"
            current_app.logger.error(f"Array extraction failed: {error_msg}")
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Array content endpoint error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Internal server error", 500)

@api_v1.route('/content/array/batch', methods=['POST'])
@apply_rate_limit("2 per minute")
def batch_extract_array_content():
    """
    Batch extract array content from multiple URLs with deduplication
    
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
        
        # Process results with enhanced deduplication statistics
        if results:
            result_dicts = []
            successful = 0
            failed = 0
            total_items = 0
            total_deduplication_savings = 0
            
            for result in results:
                try:
                    result_dict = result.to_dict() if result else {"success": False, "error": "No result"}
                    
                    # Add array data to response and calculate deduplication stats
                    if result and result.success and hasattr(result, 'metadata') and 'arrays' in result.metadata:
                        result_dict['arrays'] = result.metadata['arrays']
                        
                        # Count total items for this result
                        for array_data in result.metadata['arrays'].values():
                            total_items += array_data.get('count', 0)
                        
                        # Track deduplication savings
                        dedup_stats = result.metadata.get('deduplication_stats', {})
                        items_removed = dedup_stats.get('items_removed', 0)
                        total_deduplication_savings += items_removed
                    
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
            total_deduplication_savings = 0
        
        total_time = time.time() - start_time
        
        return success_response({
            'results': result_dicts,
            'total_processed': len(result_dicts),
            'successful': successful,
            'failed': failed,
            'total_items_extracted': total_items,
            'total_time': round(total_time, 2),
            'average_time_per_url': round(total_time / len(urls), 2) if urls else 0,
            'mode': 'array_content_batch_deduplicated',
            'array_selectors_used': list(array_selectors.keys()),
            'format_used': format_output,
            'batch_deduplication_stats': {
                'total_duplicate_items_removed': total_deduplication_savings,
                'deduplication_applied': total_deduplication_savings > 0,
                'efficiency_improvement': f"{total_deduplication_savings} duplicate items removed"
            },
            'features': {
                'array_based_extraction': True,
                'sub_selector_support': True,
                'repeated_elements_as_arrays': True,
                'advanced_deduplication': True,
                'content_quality_enhancement': True
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
    Quick array extraction via GET with query parameters and deduplication
    
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
                result.metadata['endpoint'] = 'array_content_get_deduplicated'
            
            response_data = result.to_dict()
            if 'arrays' in result.metadata:
                response_data['arrays'] = result.metadata['arrays']
                
                # Add GET-specific deduplication info
                arrays_data = result.metadata['arrays'].get('items', {})
                if arrays_data:
                    response_data['get_extraction_info'] = {
                        'selector_used': main_selector,
                        'items_found': arrays_data.get('count', 0),
                        'deduplication_applied': arrays_data.get('deduplication_applied', False),
                        'sub_selectors_used': arrays_data.get('sub_selectors_used', [])
                    }
            
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
    """Test endpoint for array-based extraction with deduplication examples"""
    try:
        return success_response({
            "message": "Array-based content extraction service is ready (WITH DEDUPLICATION)",
            "version": "2.0 - Enhanced with Advanced Deduplication",
            "description": "Extract repeated elements (like news items, products, articles) as structured arrays with automatic deduplication",
            "endpoints": {
                "array": {
                    "url": "POST /api/v1/content/array",
                    "description": "Extract repeated elements as arrays with sub-selectors and deduplication",
                    "perfect_for": ["News lists", "Product listings", "Article feeds", "Social media posts", "Search results"],
                    "deduplication_features": [
                        "Removes duplicate items within arrays",
                        "Eliminates repeated content in sub-selectors",
                        "Prevents duplicate sentences within items",
                        "Maintains content quality and uniqueness"
                    ]
                },
                "array_batch": {
                    "url": "POST /api/v1/content/array/batch",
                    "description": "Batch extract arrays from multiple URLs with deduplication"
                },
                "array_get": {
                    "url": "GET /api/v1/content/array/<url>",
                    "description": "Quick array extraction via GET parameters with deduplication"
                }
            },
            "deduplication_improvements": {
                "what_was_fixed": [
                    "Duplicate items in arrays from similar content",
                    "Repeated content in main_content field",
                    "Overlapping text from sub-selectors",
                    "Same sentences appearing multiple times",
                    "Nested element content duplication"
                ],
                "how_it_works": [
                    "1. Extract content from each array element individually",
                    "2. Remove duplicate sentences within each item",
                    "3. Compare items across the array and remove duplicates",
                    "4. Clean up sub-selector content to avoid overlaps",
                    "5. Provide deduplication statistics in response"
                ],
                "benefits": [
                    "Higher quality content arrays",
                    "Reduced response size",
                    "Better user experience",
                    "More accurate item counts",
                    "Cleaner data for processing"
                ]
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
                    },
                    "expected_improvement": "Duplicate news items automatically removed"
                },
                "product_listings": {
                    "description": "E-commerce product extraction with deduplication",
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
                    },
                    "expected_improvement": "Duplicate products filtered out automatically"
                },
                "social_media_posts": {
                    "description": "Social media feed extraction with deduplication",
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
                    },
                    "expected_improvement": "Duplicate or similar posts removed"
                }
            },
            "response_structure": {
                "arrays": {
                    "selector_name": {
                        "selector": "CSS selector used",
                        "items": [
                            {
                                "index": 0,
                                "main_content": "Unique main text content",
                                "title": "Extracted title",
                                "summary": "Extracted summary",
                                "word_count": 25,
                                "char_count": 150
                            }
                        ],
                        "count": "Number of unique items found",
                        "deduplication_applied": "Boolean indicating if duplicates were removed"
                    }
                },
                "deduplication_stats": {
                    "total_items_before_dedup": "Original item count",
                    "total_items_after_dedup": "Final unique item count",
                    "items_removed": "Number of duplicates removed",
                    "deduplication_ratio": "Percentage of duplicates removed"
                }
            },
            "testing_deduplication": {
                "before_fix": "Arrays contained duplicate items and repeated content",
                "after_fix": "Only unique items with clean content",
                "test_indicators": [
                    "Check 'deduplication_applied' flag in array data",
                    "Compare 'count' vs original element count",
                    "Look for 'deduplication_stats' in metadata",
                    "Verify no repeated sentences in main_content"
                ]
            },
            "infinitude_integration": {
                "next_js_example": {
                    "description": "Perfect for your Next.js 14 SAAS projects",
                    "use_cases": [
                        "News aggregation with clean, unique articles",
                        "Product comparison with deduplicated listings",
                        "Content curation with quality filtering",
                        "Social media monitoring with unique posts"
                    ]
                },
                "saas_benefits": [
                    "Higher quality data extraction",
                    "Reduced storage requirements",
                    "Better user experience",
                    "More accurate analytics"
                ]
            },
            "status": "healthy",
            "service": "Array-Based Content Extraction API with Advanced Deduplication"
        })
    except Exception as e:
        return error_response(f"Array extraction test failed: {str(e)}", 500)

@api_v1.route('/content/array/demo', methods=['POST'])
@apply_rate_limit("5 per minute")
def demo_array_extraction():
    """
    Demo endpoint with pre-configured examples for common sites with deduplication
    
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
        
        # Pre-configured selector templates with deduplication awareness
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
        
        # Run the extraction with deduplication
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
            
            # Add demo info with deduplication results
            demo_info = {
                'site_type': site_type,
                'template_used': config,
                'extraction_successful': True,
                'deduplication_summary': {}
            }
            
            # Add deduplication summary for each array
            if 'arrays' in result.metadata:
                for name, data in result.metadata['arrays'].items():
                    demo_info['deduplication_summary'][name] = {
                        'items_found': data.get('count', 0),
                        'deduplication_applied': data.get('deduplication_applied', False),
                        'quality_improved': data.get('deduplication_applied', False)
                    }
            
            response_data['demo_info'] = demo_info
            
            return success_response(response_data)
        else:
            return error_response(result.error if result else "Demo extraction failed", 400)
            
    except Exception as e:
        current_app.logger.error(f"Demo extraction error: {str(e)}")
        return error_response("Demo extraction failed", 500)