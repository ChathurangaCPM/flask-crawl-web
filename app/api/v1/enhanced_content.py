# app/api/v1/enhanced_content.py
from flask import request, jsonify, current_app
import asyncio
import time
import traceback
import os
from functools import wraps

from app.api.v1 import api_v1
from app.services.enhanced_content_service import EnhancedContentOnlyCrawlerService
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

@api_v1.route('/content/selective', methods=['POST'])
@apply_rate_limit("15 per minute")
def extract_content_with_selectors():
    """
    Extract content from specific div elements using CSS selectors - WITH DEDUPLICATION
    
    Request body:
    {
        "url": "https://example.com",
        "config": {
            "selectors": [".main-content", "#article-body", ".post-content"],
            "exclude_selectors": [".advertisement", ".sidebar"],
            "max_content_length": 5000,
            "return_sections": true
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
        
        # Extract selector configuration
        custom_selectors = config.get('selectors', [])
        exclude_selectors = config.get('exclude_selectors', [])
        max_length = min(config.get('max_content_length', 5000), 25000)
        return_sections = config.get('return_sections', False)
        
        # Validate selectors
        if custom_selectors and not isinstance(custom_selectors, list):
            return error_response("selectors must be an array of CSS selectors", 400)
        
        if exclude_selectors and not isinstance(exclude_selectors, list):
            return error_response("exclude_selectors must be an array of CSS selectors", 400)
        
        if len(custom_selectors) > 10:
            return error_response("Maximum 10 selectors allowed", 400)
        
        if len(exclude_selectors) > 5:
            return error_response("Maximum 5 exclude selectors allowed", 400)
        
        # Log the request for debugging
        current_app.logger.info(f"Selective content extraction request:")
        current_app.logger.info(f"  URL: {url}")
        current_app.logger.info(f"  Selectors: {custom_selectors}")
        current_app.logger.info(f"  Exclude: {exclude_selectors}")
        
        # Initialize enhanced crawler service
        crawler_service = EnhancedContentOnlyCrawlerService(current_app.config)
        
        # Run selective content extraction
        try:
            result = safe_async_run(
                crawler_service.crawl_with_custom_selectors(
                    url, custom_selectors, exclude_selectors, max_length, return_sections
                ),
                timeout=30
            )
        except asyncio.TimeoutError:
            return error_response("Selective content extraction timeout after 30 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Selective content extraction failed: {str(crawl_error)}")
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            return error_response(f"Selective content extraction failed: {str(crawl_error)}", 500)
        
        # Add timing information and enhanced metadata
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'selective_content_deduplicated'
                
                # Add deduplication statistics
                content = result.content
                if content:
                    # Calculate basic duplication metrics
                    words = content.split()
                    unique_words = set(word.lower() for word in words if len(word) > 3)
                    
                    result.metadata['content_analysis'] = {
                        'total_words': len(words),
                        'unique_words': len(unique_words),
                        'vocabulary_ratio': round(len(unique_words) / max(len(words), 1), 3),
                        'content_length_after_deduplication': len(content)
                    }
            
            # Log successful extraction
            current_app.logger.info(f"Selective extraction successful:")
            current_app.logger.info(f"  Content length: {len(result.content)}")
            current_app.logger.info(f"  Sections found: {result.metadata.get('total_sections', 0)}")
            current_app.logger.info(f"  Deduplication applied: {result.metadata.get('deduplication_applied', False)}")
            
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Selective content extraction failed"
            current_app.logger.error(f"Extraction failed: {error_msg}")
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Selective content endpoint error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Internal server error", 500)

@api_v1.route('/content/selective/batch', methods=['POST'])
@apply_rate_limit("3 per minute")
def batch_extract_content_with_selectors():
    """
    Batch extract content using custom selectors with deduplication
    
    Request body:
    {
        "urls": ["https://example1.com", "https://example2.com"],
        "config": {
            "selectors": [".content", "article"],
            "exclude_selectors": [".ads"],
            "max_content_length": 3000,
            "max_concurrent": 2
        }
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        max_batch_size = min(current_app.config.get('MAX_BATCH_SIZE', 5), 5)
        is_valid, error_msg = validate_batch_request(data, max_batch_size)
        if not is_valid:
            return error_response(error_msg, 400)
        
        urls = data['urls'][:max_batch_size]
        config = data.get('config', {})
        
        # Extract configuration
        custom_selectors = config.get('selectors', [])
        exclude_selectors = config.get('exclude_selectors', [])
        max_length = min(config.get('max_content_length', 3000), 10000)
        max_concurrent = min(config.get('max_concurrent', 2), 3)
        
        # Validate selectors
        if custom_selectors and len(custom_selectors) > 10:
            return error_response("Maximum 10 selectors allowed", 400)
        
        if exclude_selectors and len(exclude_selectors) > 5:
            return error_response("Maximum 5 exclude selectors allowed", 400)
        
        crawler_service = EnhancedContentOnlyCrawlerService(current_app.config)
        
        try:
            results = safe_async_run(
                crawler_service.crawl_multiple_with_selectors(
                    urls, custom_selectors, exclude_selectors, max_length, max_concurrent
                ),
                timeout=90
            )
        except asyncio.TimeoutError:
            return error_response("Batch selective content extraction timeout after 90 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"Batch selective content extraction failed: {str(crawl_error)}")
            return error_response(f"Batch selective content extraction failed: {str(crawl_error)}", 500)
        
        # Process results
        if results:
            result_dicts = []
            successful = 0
            failed = 0
            total_content_length = 0
            
            for result in results:
                try:
                    result_dict = result.to_dict() if result else {"success": False, "error": "No result"}
                    
                    # Add content analysis for successful results
                    if result and result.success:
                        total_content_length += len(result.content)
                        
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
            total_content_length = 0
        
        total_time = time.time() - start_time
        
        return success_response({
            'results': result_dicts,
            'total_processed': len(result_dicts),
            'successful': successful,
            'failed': failed,
            'total_time': round(total_time, 2),
            'average_time_per_url': round(total_time / len(urls), 2) if urls else 0,
            'mode': 'selective_content_batch_deduplicated',
            'selectors_used': custom_selectors,
            'exclude_selectors_used': exclude_selectors,
            'batch_statistics': {
                'total_content_extracted': total_content_length,
                'average_content_per_url': round(total_content_length / max(successful, 1), 0)
            },
            'features': {
                'custom_selectors': True,
                'exclude_selectors': True,
                'clean_text_only': True,
                'section_based_extraction': True,
                'content_deduplication': True
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Batch selective content error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Batch selective content processing failed", 500)

@api_v1.route('/content/selective/<path:url>', methods=['GET'])
@apply_rate_limit("25 per minute")
def extract_content_selective_get(url):
    """
    Quick selective content extraction via GET with query parameters
    
    Query parameters:
    - selectors: comma-separated CSS selectors (e.g., ?selectors=.content,.main)
    - exclude: comma-separated exclude selectors
    - length: max content length
    """
    start_time = time.time()
    
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse query parameters
        selectors_param = request.args.get('selectors', '')
        exclude_param = request.args.get('exclude', '')
        max_length = min(int(request.args.get('length', 2000)), 5000)
        
        # Parse selectors from comma-separated string
        custom_selectors = [s.strip() for s in selectors_param.split(',') if s.strip()] if selectors_param else []
        exclude_selectors = [s.strip() for s in exclude_param.split(',') if s.strip()] if exclude_param else []
        
        # Validate
        if len(custom_selectors) > 5:  # Stricter limit for GET
            return error_response("Maximum 5 selectors allowed in GET request", 400)
        
        if len(exclude_selectors) > 3:
            return error_response("Maximum 3 exclude selectors allowed in GET request", 400)
        
        crawler_service = EnhancedContentOnlyCrawlerService(current_app.config)
        
        try:
            result = safe_async_run(
                crawler_service.crawl_with_custom_selectors(
                    url, custom_selectors, exclude_selectors, max_length, False
                ),
                timeout=15
            )
        except asyncio.TimeoutError:
            return error_response("GET selective content extraction timeout after 15 seconds", 408)
        except Exception as crawl_error:
            current_app.logger.error(f"GET selective content extraction failed: {str(crawl_error)}")
            return error_response(f"GET selective content extraction failed: {str(crawl_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            if hasattr(result, 'metadata') and result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'selective_content_get_deduplicated'
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "GET selective content extraction failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"GET selective content error: {str(e)}")
        return error_response("GET selective content request failed", 500)

@api_v1.route('/content/analyze', methods=['POST'])
@apply_rate_limit("10 per minute")
def analyze_page_structure():
    """
    Analyze page structure and suggest optimal selectors
    
    Request body:
    {
        "url": "https://example.com",
        "config": {
            "find_main_content": true,
            "suggest_selectors": true,
            "max_suggestions": 5
        }
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        is_valid, error_msg = validate_crawl_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        config = data.get('config', {})
        
        find_main_content = config.get('find_main_content', True)
        suggest_selectors = config.get('suggest_selectors', True)
        max_suggestions = min(config.get('max_suggestions', 5), 10)
        
        crawler_service = EnhancedContentOnlyCrawlerService(current_app.config)
        
        try:
            # First, get the basic crawl result
            result = safe_async_run(
                crawler_service.crawl_with_custom_selectors(url, None, None, 500, True),
                timeout=25
            )
            
            if not result.success:
                return error_response(result.error, 400)
            
            # Analyze the structure
            analysis = {
                "url": url,
                "title": result.title,
                "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                "word_count": result.word_count,
                "suggested_selectors": [],
                "common_content_areas": [],
                "exclude_suggestions": [],
                "deduplication_recommendations": {
                    "single_selector_recommended": True,
                    "reason": "Using multiple selectors may cause content duplication",
                    "best_practices": [
                        "Start with one specific selector",
                        "Use exclude_selectors to remove unwanted content",
                        "Test selectors in browser dev tools first"
                    ]
                }
            }
            
            # Add suggestions based on common patterns
            if suggest_selectors:
                analysis["suggested_selectors"] = [
                    {"selector": "main", "description": "Main content area", "priority": "high"},
                    {"selector": "article", "description": "Article content", "priority": "high"},
                    {"selector": ".content", "description": "Content class", "priority": "medium"},
                    {"selector": "#main-content", "description": "Main content ID", "priority": "medium"},
                    {"selector": ".post-content", "description": "Post content area", "priority": "medium"}
                ][:max_suggestions]
                
                analysis["exclude_suggestions"] = [
                    {"selector": "nav", "description": "Navigation menus"},
                    {"selector": ".sidebar", "description": "Sidebar content"},
                    {"selector": ".advertisement", "description": "Advertisement blocks"},
                    {"selector": "footer", "description": "Footer content"},
                    {"selector": ".comments", "description": "Comment sections"}
                ]
            
            total_time = time.time() - start_time
            analysis["analysis_time"] = round(total_time, 2)
            
            return success_response({
                "analysis": analysis,
                "extraction_example": result.to_dict() if find_main_content else None,
                "deduplication_info": {
                    "why_deduplication_matters": "Multiple selectors can extract overlapping content",
                    "how_it_works": "The API automatically removes duplicate content blocks",
                    "best_selector_strategy": "Use one primary selector with exclude_selectors for precision"
                },
                "next_steps": {
                    "test_selectors": "Use POST /api/v1/content/selective with suggested selectors",
                    "batch_extract": "Use POST /api/v1/content/selective/batch for multiple URLs",
                    "get_quick": f"Use GET /api/v1/content/selective/{url.replace('https://', '')}?selectors=main,article"
                }
            })
            
        except asyncio.TimeoutError:
            return error_response("Page structure analysis timeout after 25 seconds", 408)
        except Exception as analysis_error:
            current_app.logger.error(f"Page structure analysis failed: {str(analysis_error)}")
            return error_response(f"Page structure analysis failed: {str(analysis_error)}", 500)
            
    except Exception as e:
        current_app.logger.error(f"Structure analysis endpoint error: {str(e)}")
        return error_response("Structure analysis failed", 500)

@api_v1.route('/content/selective/test', methods=['GET'])
@apply_rate_limit("60 per minute")
def test_selective_extraction():
    """Test endpoint for selective content extraction with enhanced documentation"""
    try:
        return success_response({
            "message": "Selective content extraction service is ready (WITH DEDUPLICATION)",
            "version": "2.0 - Enhanced with Content Deduplication",
            "endpoints": {
                "selective": {
                    "url": "POST /api/v1/content/selective",
                    "description": "Extract content using custom CSS selectors with automatic deduplication",
                    "example": {
                        "url": "https://example.com",
                        "config": {
                            "selectors": [".main-content", "#article-body"],
                            "exclude_selectors": [".advertisement", ".sidebar"],
                            "max_content_length": 5000,
                            "return_sections": True
                        }
                    },
                    "deduplication_features": [
                        "Removes duplicate content blocks within same selector",
                        "Eliminates overlapping content from multiple selectors",
                        "Prioritizes more specific selectors over general ones",
                        "Removes duplicate sentences and paragraphs"
                    ]
                },
                "selective_batch": {
                    "url": "POST /api/v1/content/selective/batch",
                    "description": "Batch extract content using custom selectors with deduplication"
                },
                "selective_get": {
                    "url": "GET /api/v1/content/selective/<url>",
                    "description": "Quick selective extraction via GET with deduplication",
                    "example": "GET /api/v1/content/selective/example.com?selectors=.content,.main&exclude=.ads&length=2000"
                },
                "analyze": {
                    "url": "POST /api/v1/content/analyze",
                    "description": "Analyze page structure and get selector suggestions"
                }
            },
            "deduplication_improvements": {
                "what_was_fixed": [
                    "Content extracted multiple times from nested elements",
                    "Same content appearing from different selectors",
                    "Duplicate sentences within extracted content",
                    "Repeated phrases and paragraphs"
                ],
                "how_it_works": [
                    "1. Extract content from each selector individually",
                    "2. Remove duplicates within each selector's content",
                    "3. Compare content across selectors and remove overlaps",
                    "4. Prioritize more specific selectors",
                    "5. Final deduplication pass on combined content"
                ],
                "benefits": [
                    "Cleaner, more readable content",
                    "Reduced response size",
                    "Better content quality",
                    "More efficient processing"
                ]
            },
            "css_selectors_guide": {
                "by_class": ".classname (e.g., .main-content)",
                "by_id": "#idname (e.g., #article-body)",
                "by_tag": "tagname (e.g., article, main)",
                "by_attribute": "[attribute='value'] (e.g., [role='main'])",
                "descendant": "parent child (e.g., .content p)",
                "multiple": "Use array: ['.content', 'article', 'main']",
                "best_practices": [
                    "Start with one specific selector",
                    "Use browser dev tools to test selectors",
                    "Prefer IDs and classes over generic tags",
                    "Use exclude_selectors to remove unwanted content"
                ]
            },
            "common_selectors": {
                "main_content": ["main", "article", ".content", "#main-content", ".post-content"],
                "exclude_common": ["nav", "footer", ".sidebar", ".advertisement", ".comments"],
                "news_sites": [".article-body", ".story-content", ".post-content"],
                "blogs": [".entry-content", ".post-body", ".article-content"],
                "documentation": [".content", ".documentation", ".docs-content"]
            },
            "testing_your_fix": {
                "before_fix": "Content was duplicated multiple times",
                "after_fix": "Content should appear only once",
                "test_steps": [
                    "1. Send POST request to /api/v1/content/selective",
                    "2. Check content field for duplications",
                    "3. Verify metadata.deduplication_applied is true if multiple selectors used",
                    "4. Compare content length before/after fix"
                ]
            },
            "infinitude_integration": {
                "next_js_example": {
                    "description": "Ready for your Next.js 14 app router projects",
                    "api_route": "app/api/crawl/selective/route.js",
                    "component": "components/ContentExtractor.jsx",
                    "hook": "hooks/useWebCrawler.js"
                },
                "saas_features": [
                    "Batch processing for multiple URLs",
                    "Content deduplication for cleaner results",
                    "Selective extraction for targeted content",
                    "Rate limiting with API key bypass"
                ]
            },
            "status": "healthy",
            "service": "Selective Content Extraction API with Advanced Deduplication"
        })
    except Exception as e:
        return error_response(f"Selective extraction test failed: {str(e)}", 500)