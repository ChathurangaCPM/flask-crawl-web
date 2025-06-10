import asyncio
import logging
import random
import time
import json
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from dataclasses import dataclass, field

# Try to import CacheMode, fallback if not available
try:
    from crawl4ai.async_configs import CacheMode
    CACHE_ENABLED = CacheMode.ENABLED
    CACHE_DISABLED = CacheMode.DISABLED
except ImportError:
    CACHE_ENABLED = True
    CACHE_DISABLED = False

from app.utils.validators import validate_url

logger = logging.getLogger(__name__)

@dataclass
class ProductData:
    """Data structure for a single product"""
    name: str = ""
    price: str = ""
    sale_price: str = ""
    original_price: str = ""
    image_url: str = ""
    product_url: str = ""
    availability: str = ""
    rating: str = ""
    reviews_count: str = ""
    description: str = ""
    brand: str = ""
    sku: str = ""
    discount_percentage: str = ""
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'name': self.name,
            'price': self.price,
            'sale_price': self.sale_price,
            'original_price': self.original_price,
            'image_url': self.image_url,
            'product_url': self.product_url,
            'availability': self.availability,
            'rating': self.rating,
            'reviews_count': self.reviews_count,
            'description': self.description,
            'brand': self.brand,
            'sku': self.sku,
            'discount_percentage': self.discount_percentage,
            'additional_data': self.additional_data
        }

@dataclass
class EcommerceScrapingResult:
    """Result of e-commerce scraping operation"""
    success: bool
    url: str
    products: List[ProductData] = field(default_factory=list)
    total_products: int = 0
    page_title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'success': self.success,
            'url': self.url,
            'products': [product.to_dict() for product in self.products],
            'total_products': self.total_products,
            'page_title': self.page_title,
            'metadata': self.metadata,
            'error': self.error
        }

class EcommerceProductScraper:
    """Specialized scraper for e-commerce product listings"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 45)
        
        # E-commerce optimized user agents
        self.ecommerce_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
        ]
        
        # Headers that work well with e-commerce sites
        self.ecommerce_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
    
    def create_ecommerce_browser_config(self) -> BrowserConfig:
        """Create browser configuration optimized for e-commerce"""
        return BrowserConfig(
            verbose=False,
            headless=True,
            browser_type="chromium",
            user_agent=random.choice(self.ecommerce_user_agents),
            headers=self.ecommerce_headers,
            viewport_width=1920,
            viewport_height=1080,
            ignore_https_errors=True,
            java_script_enabled=True,  # E-commerce sites often need JS
            accept_downloads=False,
            extra_args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--allow-running-insecure-content',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
            ]
        )
    
    def create_ecommerce_run_config(self, selector: str = None) -> CrawlerRunConfig:
        """Create run configuration optimized for e-commerce"""
        return CrawlerRunConfig(
            word_count_threshold=1,
            excluded_tags=[],  # Don't exclude much for e-commerce
            exclude_external_links=False,
            process_iframes=False,
            remove_overlay_elements=True,
            delay_before_return_html=3.0,  # Wait for products to load
            wait_for=selector if selector else None,  # Wait for product container
            magic=True,  # Enable magic mode for better extraction
        )
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text.strip())
        # Remove special characters but keep currency symbols
        text = re.sub(r'[^\w\s\$\€\£\¥\₹\.,\-\%]', '', text)
        return text.strip()
    
    def extract_price(self, price_text: str) -> Dict[str, str]:
        """Extract price information from text"""
        if not price_text:
            return {'price': '', 'sale_price': '', 'original_price': ''}
        
        # Clean the price text
        price_text = self.clean_text(price_text)
        
        # Look for currency symbols and numbers
        price_pattern = r'[\$\€\£\¥\₹]?[\d,]+\.?\d*'
        prices = re.findall(price_pattern, price_text)
        
        if len(prices) >= 2:
            # Assume first is sale price, second is original price
            return {
                'price': prices[0],
                'sale_price': prices[0],
                'original_price': prices[1]
            }
        elif len(prices) == 1:
            return {
                'price': prices[0],
                'sale_price': '',
                'original_price': ''
            }
        else:
            return {
                'price': price_text,
                'sale_price': '',
                'original_price': ''
            }
    
    def calculate_discount_percentage(self, sale_price: str, original_price: str) -> str:
        """Calculate discount percentage"""
        try:
            if not sale_price or not original_price:
                return ""
            
            # Extract numeric values
            sale_num = float(re.sub(r'[^\d.]', '', sale_price))
            orig_num = float(re.sub(r'[^\d.]', '', original_price))
            
            if orig_num > sale_num > 0:
                discount = ((orig_num - sale_num) / orig_num) * 100
                return f"{discount:.0f}%"
            
            return ""
        except:
            return ""
    
    async def scrape_products(self, url: str, product_selector: str, 
                            name_selector: str = None, 
                            price_selector: str = None,
                            image_selector: str = None,
                            link_selector: str = None) -> EcommerceScrapingResult:
        """Scrape products from e-commerce site"""
        start_time = time.time()
        
        try:
            if not validate_url(url):
                return EcommerceScrapingResult(
                    success=False,
                    url=url,
                    error="Invalid URL format"
                )
            
            # Add delay to be respectful
            await asyncio.sleep(random.uniform(1.0, 3.0))
            
            browser_config = self.create_ecommerce_browser_config()
            run_config = self.create_ecommerce_run_config(product_selector)
            
            async with AsyncWebCrawler(config=browser_config) as crawler:
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=self.default_timeout
                    )
                    
                    if result.success:
                        products = await self._extract_products_from_result(
                            result, url, product_selector, 
                            name_selector, price_selector, 
                            image_selector, link_selector
                        )
                        
                        crawl_time = time.time() - start_time
                        
                        return EcommerceScrapingResult(
                            success=True,
                            url=url,
                            products=products,
                            total_products=len(products),
                            page_title=getattr(result, 'title', ''),
                            metadata={
                                'crawl_time': round(crawl_time, 2),
                                'status_code': getattr(result, 'status_code', None),
                                'product_selector': product_selector,
                                'extraction_method': 'css_selector'
                            }
                        )
                    else:
                        return EcommerceScrapingResult(
                            success=False,
                            url=url,
                            error=result.error_message or "Failed to load page"
                        )
                
                except asyncio.TimeoutError:
                    return EcommerceScrapingResult(
                        success=False,
                        url=url,
                        error=f"Timeout after {self.default_timeout}s - page took too long to load"
                    )
                
                except Exception as crawl_error:
                    logger.error(f"E-commerce scraping error for {url}: {str(crawl_error)}")
                    return EcommerceScrapingResult(
                        success=False,
                        url=url,
                        error=f"Scraping failed: {str(crawl_error)}"
                    )

        except Exception as e:
            logger.error(f"E-commerce scraper setup error for {url}: {str(e)}")
            return EcommerceScrapingResult(
                success=False,
                url=url,
                error=f"Setup error: {str(e)}"
            )
    
    async def _extract_products_from_result(self, result, base_url: str, 
                                          product_selector: str,
                                          name_selector: str = None,
                                          price_selector: str = None,
                                          image_selector: str = None,
                                          link_selector: str = None) -> List[ProductData]:
        """Extract product data from crawl result"""
        products = []
        
        try:
            # Try to extract from structured data first (JSON-LD)
            structured_products = self._extract_from_structured_data(result)
            if structured_products:
                products.extend(structured_products)
            
            # Extract from HTML using CSS selectors
            html_products = self._extract_from_html(
                result, base_url, product_selector,
                name_selector, price_selector, 
                image_selector, link_selector
            )
            
            # Merge or use HTML products if no structured data
            if not products:
                products = html_products
            
            # Remove duplicates based on name or URL
            seen = set()
            unique_products = []
            for product in products:
                identifier = product.name.lower() + product.product_url
                if identifier not in seen:
                    seen.add(identifier)
                    unique_products.append(product)
            
            return unique_products[:50]  # Limit to 50 products
            
        except Exception as e:
            logger.error(f"Product extraction error: {str(e)}")
            return []
    
    def _extract_from_structured_data(self, result) -> List[ProductData]:
        """Extract products from JSON-LD structured data"""
        products = []
        
        try:
            # Look for JSON-LD in the HTML
            html_content = getattr(result, 'html', '')
            if not html_content:
                return products
            
            # Find JSON-LD scripts
            json_ld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
            json_scripts = re.findall(json_ld_pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            for script in json_scripts:
                try:
                    data = json.loads(script.strip())
                    
                    # Handle different structured data formats
                    if isinstance(data, list):
                        for item in data:
                            product = self._parse_structured_product(item)
                            if product:
                                products.append(product)
                    elif isinstance(data, dict):
                        product = self._parse_structured_product(data)
                        if product:
                            products.append(product)
                            
                except json.JSONDecodeError:
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Structured data extraction error: {str(e)}")
            return products
    
    def _parse_structured_product(self, data: Dict) -> Optional[ProductData]:
        """Parse a single product from structured data"""
        try:
            if data.get('@type') in ['Product', 'ProductModel']:
                product = ProductData()
                
                product.name = self.clean_text(data.get('name', ''))
                product.description = self.clean_text(data.get('description', ''))
                product.brand = self.clean_text(data.get('brand', {}).get('name', ''))
                product.sku = self.clean_text(data.get('sku', ''))
                
                # Extract offers/price information
                offers = data.get('offers', {})
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                
                if offers:
                    product.price = self.clean_text(str(offers.get('price', '')))
                    product.availability = self.clean_text(offers.get('availability', ''))
                    product.product_url = offers.get('url', '')
                
                # Extract image
                image = data.get('image', '')
                if isinstance(image, list) and image:
                    image = image[0]
                if isinstance(image, dict):
                    image = image.get('url', '')
                product.image_url = image
                
                # Extract rating
                rating = data.get('aggregateRating', {})
                if rating:
                    product.rating = str(rating.get('ratingValue', ''))
                    product.reviews_count = str(rating.get('reviewCount', ''))
                
                return product if product.name else None
                
        except Exception as e:
            logger.error(f"Structured product parsing error: {str(e)}")
            return None
    
    def _extract_from_html(self, result, base_url: str, product_selector: str,
                          name_selector: str = None, price_selector: str = None,
                          image_selector: str = None, link_selector: str = None) -> List[ProductData]:
        """Extract products from HTML using CSS selectors (simplified version)"""
        products = []
        
        try:
            # This is a simplified text-based extraction
            # In a full implementation, you'd use BeautifulSoup or similar
            markdown = getattr(result, 'markdown', '')
            
            if markdown and product_selector:
                # Simple text-based extraction as fallback
                lines = markdown.split('\n')
                current_product = None
                
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 10:  # Potential product name
                        if current_product:
                            products.append(current_product)
                        
                        current_product = ProductData()
                        current_product.name = self.clean_text(line[:100])
                        
                        # Look for price patterns in the line
                        price_info = self.extract_price(line)
                        current_product.price = price_info['price']
                        current_product.sale_price = price_info['sale_price']
                        current_product.original_price = price_info['original_price']
                        
                        # Calculate discount if both prices exist
                        if current_product.sale_price and current_product.original_price:
                            current_product.discount_percentage = self.calculate_discount_percentage(
                                current_product.sale_price, current_product.original_price
                            )
                
                if current_product:
                    products.append(current_product)
            
            return products[:20]  # Limit for fallback method
            
        except Exception as e:
            logger.error(f"HTML extraction error: {str(e)}")
            return products