from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import asyncio
import time
import traceback
from app.services.ecommerce_scraper import EcommerceProductScraper
from app.utils.validators import validate_url
from app.utils.response_helpers import success_response, error_response

# Create separate blueprint for e-commerce
ecommerce_bp = Blueprint('ecommerce', __name__)

# Initialize rate limiter for e-commerce with in-memory storage
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["50 per hour", "10 per minute"],
    storage_uri="memory://",  # Use in-memory storage (no Redis)
    strategy="fixed-window"
)

def safe_async_run(coro, timeout=60):
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

def validate_ecommerce_request(data):
    """Validate e-commerce scraping request"""
    if not data:
        return False, "Request body is required"
    
    url = data.get('url')
    if not url:
        return False, "URL is required"
    
    if not validate_url(url):
        return False, "Invalid URL format"
    
    product_selector = data.get('product_selector')
    if not product_selector:
        return False, "Product selector is required"
    
    # Basic CSS selector validation
    if not isinstance(product_selector, str) or len(product_selector.strip()) < 2:
        return False, "Product selector must be a valid CSS selector"
    
    return True, None

@ecommerce_bp.route('/health', methods=['GET'])
def ecommerce_health():
    """Health check for e-commerce scraper"""
    try:
        return success_response({
            "status": "healthy",
            "service": "E-commerce Product Scraper",
            "version": "1.0.0",
            "rate_limiting": "in-memory (no Redis required)",
            "endpoints": {
                "products": "POST /api/v1/ecommerce/products",
                "quick": "POST /api/v1/ecommerce/products/quick",
                "selectors": "POST /api/v1/ecommerce/selectors/detect",
                "platforms": "GET /api/v1/ecommerce/platforms"
            }
        })
    except Exception as e:
        return error_response(f"Health check failed: {str(e)}", 500)

@ecommerce_bp.route('/products', methods=['POST'])
def scrape_ecommerce_products():
    """Scrape products from e-commerce website"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate request
        is_valid, error_msg = validate_ecommerce_request(data)
        if not is_valid:
            return error_response(error_msg, 400)
        
        url = data['url']
        product_selector = data['product_selector']
        
        # Optional selectors for specific product elements
        name_selector = data.get('name_selector')
        price_selector = data.get('price_selector')
        image_selector = data.get('image_selector')
        link_selector = data.get('link_selector')
        
        # Configuration options
        config = data.get('config', {})
        max_products = min(config.get('max_products', 50), 100)  # Cap at 100
        timeout = min(config.get('timeout', 60), 120)  # Cap at 2 minutes
        
        # Initialize e-commerce scraper
        scraper = EcommerceProductScraper(current_app.config)
        
        # Run scraping
        try:
            result = safe_async_run(
                scraper.scrape_products(
                    url=url,
                    product_selector=product_selector,
                    name_selector=name_selector,
                    price_selector=price_selector,
                    image_selector=image_selector,
                    link_selector=link_selector
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return error_response(f"Scraping timeout after {timeout} seconds", 408)
        except Exception as scrape_error:
            current_app.logger.error(f"E-commerce scraping failed: {str(scrape_error)}")
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            return error_response(f"Scraping failed: {str(scrape_error)}", 500)
        
        # Add timing information
        total_time = time.time() - start_time
        if result and result.success:
            # Limit products if requested
            if max_products and len(result.products) > max_products:
                result.products = result.products[:max_products]
                result.total_products = len(result.products)
            
            if result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['requested_max_products'] = max_products
                result.metadata['endpoint'] = 'ecommerce_products'
            
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Product scraping failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"E-commerce endpoint error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response("Internal server error", 500)

@ecommerce_bp.route('/products/quick', methods=['POST'])
def quick_scrape_products():
    """Quick product scraping with common selectors"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Basic validation
        url = data.get('url')
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Try to detect platform and use common selectors
        platform = data.get('platform', 'auto')
        product_selector = data.get('product_selector')
        
        # Common selectors for popular platforms
        common_selectors = {
            'shopify': '.product-item, .product-card, .grid-product, .product',
            'woocommerce': '.product, .woocommerce-LoopProduct-link',
            'magento': '.product-item, .item',
            'opencart': '.product-thumb, .product-layout',
            'prestashop': '.product-miniature, .ajax_block_product',
            'bigcommerce': '.product, .card',
            'generic': '.product, .item, .card, [data-product], [class*="product"]'
        }
        
        if not product_selector:
            if platform in common_selectors:
                product_selector = common_selectors[platform]
            else:
                product_selector = common_selectors['generic']
        
        # Initialize scraper
        scraper = EcommerceProductScraper(current_app.config)
        
        try:
            result = safe_async_run(
                scraper.scrape_products(
                    url=url,
                    product_selector=product_selector
                ),
                timeout=45  # Shorter timeout for quick scraping
            )
        except asyncio.TimeoutError:
            return error_response("Quick scraping timeout after 45 seconds", 408)
        except Exception as scrape_error:
            current_app.logger.error(f"Quick scraping failed: {str(scrape_error)}")
            return error_response(f"Quick scraping failed: {str(scrape_error)}", 500)
        
        total_time = time.time() - start_time
        if result and result.success:
            # Limit to 20 products for quick scraping
            if len(result.products) > 20:
                result.products = result.products[:20]
                result.total_products = len(result.products)
            
            if result.metadata:
                result.metadata['api_response_time'] = round(total_time, 2)
                result.metadata['endpoint'] = 'quick_products'
                result.metadata['platform_detected'] = platform
                result.metadata['selector_used'] = product_selector
            
            return success_response(result.to_dict())
        else:
            error_msg = result.error if result else "Quick scraping failed"
            return error_response(error_msg, 400)
            
    except Exception as e:
        current_app.logger.error(f"Quick scraping error: {str(e)}")
        return error_response("Quick scraping failed", 500)

@ecommerce_bp.route('/selectors/detect', methods=['POST'])
def detect_selectors():
    """Detect and suggest common selectors for a page"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url or not validate_url(url):
            return error_response("Valid URL is required", 400)
        
        # Detect platform from URL
        platform = 'generic'
        domain = url.lower()
        
        if 'shopify' in domain or '.myshopify.com' in domain:
            platform = 'shopify'
        elif 'woocommerce' in domain or '/wp-content/' in domain:
            platform = 'woocommerce'
        elif 'magento' in domain:
            platform = 'magento'
        elif 'bigcommerce' in domain:
            platform = 'bigcommerce'
        elif 'prestashop' in domain:
            platform = 'prestashop'
        
        # Platform-specific selector suggestions
        platform_selectors = {
            'shopify': {
                'product_selectors': [
                    '.product-item',
                    '.product-card',
                    '.grid-product',
                    '.product',
                    '[data-product-id]'
                ],
                'name_selectors': [
                    '.product__title',
                    '.product-title',
                    '.product-card__title',
                    'h3'
                ],
                'price_selectors': [
                    '.price',
                    '.product__price',
                    '.money',
                    '.price-item'
                ]
            },
            'woocommerce': {
                'product_selectors': [
                    '.product',
                    '.woocommerce-LoopProduct-link',
                    '.product-small',
                    '.product-item'
                ],
                'name_selectors': [
                    '.woocommerce-loop-product__title',
                    'h2',
                    '.product-title'
                ],
                'price_selectors': [
                    '.price',
                    '.woocommerce-Price-amount',
                    '.amount'
                ]
            },
            'generic': {
                'product_selectors': [
                    '.product',
                    '.item',
                    '.card',
                    '[data-product]',
                    '[class*="product"]'
                ],
                'name_selectors': [
                    '.title',
                    '.name',
                    'h2',
                    'h3',
                    '.product-name'
                ],
                'price_selectors': [
                    '.price',
                    '.cost',
                    '.amount',
                    '[class*="price"]'
                ]
            }
        }
        
        selectors = platform_selectors.get(platform, platform_selectors['generic'])
        
        return success_response({
            "url": url,
            "detected_platform": platform,
            "suggested_selectors": selectors,
            "testing_tips": [
                "Open browser dev tools (F12)",
                "Use 'Inspect Element' on products",
                "Test selectors in console: document.querySelectorAll('.selector')",
                "Look for unique class names or data attributes",
                "Start with broader selectors and refine"
            ],
            "example_test": {
                "description": "Test in browser console",
                "commands": [
                    "document.querySelectorAll('.product').length",
                    "document.querySelector('.product .title')?.textContent",
                    "document.querySelector('.product .price')?.textContent"
                ]
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Selector detection error: {str(e)}")
        return error_response("Selector detection failed", 500)

@ecommerce_bp.route('/platforms', methods=['GET'])
def supported_platforms():
    """Get list of supported e-commerce platforms"""
    try:
        return success_response({
            "supported_platforms": {
                "shopify": {
                    "name": "Shopify",
                    "common_domains": [".myshopify.com", "powered by Shopify"],
                    "typical_selectors": {
                        "products": ".product-item, .product-card",
                        "name": ".product__title, .product-title",
                        "price": ".price, .money"
                    }
                },
                "woocommerce": {
                    "name": "WooCommerce (WordPress)",
                    "common_domains": ["wp-content", "woocommerce"],
                    "typical_selectors": {
                        "products": ".product, .woocommerce-LoopProduct-link",
                        "name": ".woocommerce-loop-product__title",
                        "price": ".price, .woocommerce-Price-amount"
                    }
                },
                "magento": {
                    "name": "Magento",
                    "common_domains": ["magento"],
                    "typical_selectors": {
                        "products": ".product-item, .item",
                        "name": ".product-item-name",
                        "price": ".price-box .price"
                    }
                },
                "bigcommerce": {
                    "name": "BigCommerce",
                    "common_domains": ["bigcommerce"],
                    "typical_selectors": {
                        "products": ".product, .card",
                        "name": ".card-title",
                        "price": ".price"
                    }
                },
                "generic": {
                    "name": "Generic/Custom",
                    "description": "For custom or unknown platforms",
                    "typical_selectors": {
                        "products": ".product, .item, .card",
                        "name": ".title, .name, h2, h3",
                        "price": ".price, .cost, .amount"
                    }
                }
            },
            "rate_limiting_info": {
                "storage": "in-memory",
                "redis_required": False,
                "limits": {
                    "products": "5 per minute",
                    "quick": "10 per minute",
                    "general": "50 per hour"
                }
            }
        })
    except Exception as e:
        return error_response(f"Platform info failed: {str(e)}", 500)