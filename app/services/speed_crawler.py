import asyncio
import logging
import random
import time
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from dataclasses import dataclass, field
from enum import Enum

# Try to import CacheMode, fallback if not available
try:
    from crawl4ai.async_configs import CacheMode
    CACHE_ENABLED = CacheMode.ENABLED
    CACHE_DISABLED = CacheMode.DISABLED
except ImportError:
    CACHE_ENABLED = True
    CACHE_DISABLED = False

try:
    from app.utils.validators import validate_url
except ImportError:
    def validate_url(url: str) -> bool:
        """Fallback URL validator"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

logger = logging.getLogger(__name__)

class CrawlSpeed(Enum):
    """Crawling speed tiers for different performance needs"""
    ULTRA_FAST = "ultra_fast"
    FAST = "fast"
    NORMAL = "normal"
    THOROUGH = "thorough"

@dataclass
class SpeedConfig:
    """Configuration for different speed tiers"""
    timeout: int
    word_count_threshold: int
    excluded_tags: List[str]
    delay_before_return: float
    wait_for_images: bool
    wait_for_js: bool
    remove_overlay: bool
    process_iframes: bool
    headless: bool
    javascript_enabled: bool
    max_content_length: int
    user_simulation: bool
    extra_args: List[str] = field(default_factory=list)

class SpeedOptimizedCrawler:
    """High-performance crawler with configurable speed tiers"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 30)
        
        # Speed-optimized user agents (faster, lighter)
        self.speed_user_agents = [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # Performance-focused headers
        self.speed_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        # Speed tier configurations
        self.speed_configs = {
            CrawlSpeed.ULTRA_FAST: SpeedConfig(
                timeout=8,
                word_count_threshold=1,
                excluded_tags=['script', 'style', 'noscript', 'iframe', 'frame', 'object', 'embed', 'applet', 'form', 'input', 'button', 'select', 'textarea', 'nav', 'header', 'footer', 'aside', 'meta', 'link'],
                delay_before_return=0.1,
                wait_for_images=False,
                wait_for_js=False,
                remove_overlay=False,
                process_iframes=False,
                headless=True,
                javascript_enabled=False,  # Disable JS for maximum speed
                max_content_length=1000,
                user_simulation=False,
                extra_args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-images',
                    '--disable-javascript',
                    '--disable-background-timer-throttling',
                    '--disable-background-networking',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-features=TranslateUI,BlinkGenPropertyTrees',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--no-first-run',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            ),
            CrawlSpeed.FAST: SpeedConfig(
                timeout=15,
                word_count_threshold=3,
                excluded_tags=['script', 'style', 'noscript', 'iframe', 'frame', 'object', 'embed', 'form', 'nav', 'header', 'footer', 'aside'],
                delay_before_return=0.5,
                wait_for_images=False,
                wait_for_js=False,
                remove_overlay=True,
                process_iframes=False,
                headless=True,
                javascript_enabled=True,
                max_content_length=2500,
                user_simulation=False,
                extra_args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-images',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-gpu'
                ]
            ),
            CrawlSpeed.NORMAL: SpeedConfig(
                timeout=30,
                word_count_threshold=5,
                excluded_tags=['script', 'style', 'noscript', 'form', 'nav', 'header', 'footer'],
                delay_before_return=1.0,
                wait_for_images=False,
                wait_for_js=True,
                remove_overlay=True,
                process_iframes=False,
                headless=True,
                javascript_enabled=True,
                max_content_length=5000,
                user_simulation=False,
                extra_args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--no-first-run'
                ]
            ),
            CrawlSpeed.THOROUGH: SpeedConfig(
                timeout=60,
                word_count_threshold=10,
                excluded_tags=['script', 'style'],
                delay_before_return=2.0,
                wait_for_images=True,
                wait_for_js=True,
                remove_overlay=True,
                process_iframes=True,
                headless=True,
                javascript_enabled=True,
                max_content_length=10000,
                user_simulation=True,
                extra_args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--no-first-run'
                ]
            )
        }
    
    def get_speed_config(self, speed: CrawlSpeed) -> SpeedConfig:
        """Get configuration for specified speed tier"""
        return self.speed_configs.get(speed, self.speed_configs[CrawlSpeed.NORMAL])
    
    def create_speed_browser_config(self, speed: CrawlSpeed) -> BrowserConfig:
        """Create browser configuration optimized for specified speed"""
        config = self.get_speed_config(speed)
        
        return BrowserConfig(
            verbose=False,
            headless=config.headless,
            browser_type="chromium",
            user_agent=random.choice(self.speed_user_agents),
            headers=self.speed_headers,
            viewport_width=1280,  # Smaller viewport for speed
            viewport_height=720,
            ignore_https_errors=True,
            java_script_enabled=config.javascript_enabled,
            accept_downloads=False,
            extra_args=config.extra_args
        )
    
    def create_speed_run_config(self, speed: CrawlSpeed, css_selector: str = None) -> CrawlerRunConfig:
        """Create run configuration optimized for specified speed"""
        config = self.get_speed_config(speed)
        
        try:
            return CrawlerRunConfig(
                word_count_threshold=config.word_count_threshold,
                excluded_tags=config.excluded_tags,
                exclude_external_links=True,
                process_iframes=config.process_iframes,
                remove_overlay_elements=config.remove_overlay,
                delay_before_return_html=config.delay_before_return,
                wait_for=css_selector if css_selector else None,
                magic=speed != CrawlSpeed.ULTRA_FAST,  # Disable magic for ultra-fast
                css_selector=css_selector,
                simulate_user=config.user_simulation
            )
        except Exception as e:
            logger.warning(f"Error creating run config with advanced options: {e}")
            # Fallback to basic config
            return CrawlerRunConfig(
                word_count_threshold=config.word_count_threshold,
                excluded_tags=config.excluded_tags,
                exclude_external_links=True,
                process_iframes=config.process_iframes,
                remove_overlay_elements=config.remove_overlay,
                delay_before_return_html=config.delay_before_return
            )
    
    async def crawl_with_speed(self, url: str, speed: CrawlSpeed = CrawlSpeed.FAST, 
                              css_selector: str = None, custom_config: Dict = None) -> Dict[str, Any]:
        """Crawl URL with specified speed tier"""
        start_time = time.time()
        
        try:
            if not validate_url(url):
                return {
                    'success': False,
                    'url': url,
                    'error': 'Invalid URL format',
                    'speed_tier': speed.value
                }
            
            # Get speed configuration
            speed_config = self.get_speed_config(speed)
            
            # Override with custom config if provided
            if custom_config:
                if 'max_content_length' in custom_config and custom_config['max_content_length']:
                    speed_config.max_content_length = min(
                        custom_config['max_content_length'], 
                        speed_config.max_content_length
                    )
                if 'timeout' in custom_config and custom_config['timeout']:
                    speed_config.timeout = min(
                        custom_config['timeout'],
                        speed_config.timeout
                    )
            
            # Minimal delay for respectful crawling (but very short for speed)
            if speed != CrawlSpeed.ULTRA_FAST:
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            browser_config = self.create_speed_browser_config(speed)
            run_config = self.create_speed_run_config(speed, css_selector)
            
            async with AsyncWebCrawler(config=browser_config) as crawler:
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=speed_config.timeout
                    )
                    
                    crawl_time = time.time() - start_time
                    
                    if result.success:
                        # Truncate content if too long for speed
                        content = result.markdown or ''
                        if len(content) > speed_config.max_content_length:
                            content = content[:speed_config.max_content_length] + '...'
                        
                        return {
                            'success': True,
                            'url': url,
                            'title': getattr(result, 'title', ''),
                            'content': content,
                            'links': getattr(result, 'links', {}) if speed != CrawlSpeed.ULTRA_FAST else {},
                            'metadata': {
                                'crawl_time': round(crawl_time, 2),
                                'speed_tier': speed.value,
                                'status_code': getattr(result, 'status_code', None),
                                'content_length': len(content),
                                'javascript_enabled': speed_config.javascript_enabled,
                                'timeout_used': speed_config.timeout,
                                'performance_optimized': True
                            }
                        }
                    else:
                        return {
                            'success': False,
                            'url': url,
                            'error': result.error_message or 'Crawling failed',
                            'speed_tier': speed.value,
                            'crawl_time': round(crawl_time, 2)
                        }
                
                except asyncio.TimeoutError:
                    return {
                        'success': False,
                        'url': url,
                        'error': f'Timeout after {speed_config.timeout}s ({speed.value} mode)',
                        'speed_tier': speed.value,
                        'crawl_time': round(time.time() - start_time, 2)
                    }
                
                except Exception as crawl_error:
                    logger.error(f"Speed crawl error for {url} ({speed.value}): {str(crawl_error)}")
                    return {
                        'success': False,
                        'url': url,
                        'error': f'Crawl failed ({speed.value}): {str(crawl_error)}',
                        'speed_tier': speed.value,
                        'crawl_time': round(time.time() - start_time, 2)
                    }

        except Exception as e:
            logger.error(f"Speed crawler setup error for {url} ({speed.value}): {str(e)}")
            return {
                'success': False,
                'url': url,
                'error': f'Setup error ({speed.value}): {str(e)}',
                'speed_tier': speed.value,
                'crawl_time': round(time.time() - start_time, 2)
            }
    
    async def batch_crawl_with_speed(self, urls: List[str], speed: CrawlSpeed = CrawlSpeed.FAST,
                                   max_concurrent: int = None) -> List[Dict[str, Any]]:
        """Batch crawl multiple URLs with specified speed tier"""
        if not urls:
            return []
        
        # Determine concurrency based on speed tier
        if max_concurrent is None:
            concurrency_map = {
                CrawlSpeed.ULTRA_FAST: 10,
                CrawlSpeed.FAST: 8,
                CrawlSpeed.NORMAL: 5,
                CrawlSpeed.THOROUGH: 3
            }
            max_concurrent = concurrency_map.get(speed, 5)
        
        # Limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_semaphore(url):
            async with semaphore:
                return await self.crawl_with_speed(url, speed)
        
        # Execute batch crawling
        tasks = [crawl_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'success': False,
                    'url': urls[i],
                    'error': f'Batch processing error: {str(result)}',
                    'speed_tier': speed.value
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_speed_recommendations(self, use_case: str) -> CrawlSpeed:
        """Get recommended speed tier based on use case"""
        recommendations = {
            'monitoring': CrawlSpeed.ULTRA_FAST,
            'status_check': CrawlSpeed.ULTRA_FAST,
            'health_check': CrawlSpeed.ULTRA_FAST,
            'quick_scan': CrawlSpeed.FAST,
            'content_extraction': CrawlSpeed.FAST,
            'api_integration': CrawlSpeed.FAST,
            'data_scraping': CrawlSpeed.NORMAL,
            'seo_analysis': CrawlSpeed.NORMAL,
            'research': CrawlSpeed.THOROUGH,
            'compliance_check': CrawlSpeed.THOROUGH
        }
        return recommendations.get(use_case.lower(), CrawlSpeed.NORMAL)

# Helper functions for e-commerce processing
def extract_basic_products_from_text(content: str, selector: str) -> List[Dict]:
    """Extract basic product info from text content"""
    products = []
    
    # Simple text-based extraction for ultra-fast mode
    lines = content.split('\n')
    current_product = None
    
    for line in lines:
        line = line.strip()
        if len(line) > 10 and any(keyword in line.lower() for keyword in ['product', 'item', '$', '€', '£']):
            if current_product:
                products.append(current_product)
            
            current_product = {
                'name': line[:100],
                'price': extract_price_from_line(line),
                'source': 'ultra_fast_extraction'
            }
    
    if current_product:
        products.append(current_product)
    
    return products[:15]  # Limit for ultra-fast

def extract_enhanced_products_from_text(content: str, product_selector: str, 
                                      name_selector: str = None, price_selector: str = None) -> List[Dict]:
    """Extract enhanced product info for fast mode"""
    products = []
    
    # More sophisticated extraction for fast mode
    lines = content.split('\n')
    product_blocks = []
    current_block = []
    
    for line in lines:
        line = line.strip()
        if line:
            current_block.append(line)
            if len(current_block) > 5:  # Group lines into product blocks
                product_blocks.append('\n'.join(current_block))
                current_block = []
    
    for block in product_blocks:
        if any(keyword in block.lower() for keyword in ['product', 'buy', 'price', '$', '€']):
            product = extract_product_from_block(block)
            if product:
                products.append(product)
    
    return products[:25]  # Higher limit for fast mode

def extract_price_from_line(line: str) -> str:
    """Extract price from a text line"""
    price_pattern = r'[\$\€\£\¥\₹]?[\d,]+\.?\d*'
    prices = re.findall(price_pattern, line)
    return prices[0] if prices else ''

def extract_product_from_block(block: str) -> Dict:
    """Extract product info from a text block"""
    lines = block.split('\n')
    
    product = {
        'name': '',
        'price': '',
        'description': '',
        'source': 'fast_extraction'
    }
    
    for line in lines:
        line = line.strip()
        if not product['name'] and len(line) > 5 and len(line) < 100:
            product['name'] = line
        elif '$' in line or '€' in line or '£' in line:
            product['price'] = extract_price_from_line(line)
        elif len(line) > 20 and not product['description']:
            product['description'] = line[:200]
    
    return product if product['name'] else None