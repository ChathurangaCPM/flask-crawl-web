import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

# Try to import CacheMode, fallback if not available
try:
    from crawl4ai.async_configs import CacheMode
    CACHE_ENABLED = CacheMode.ENABLED
    CACHE_DISABLED = CacheMode.DISABLED
except ImportError:
    CACHE_ENABLED = True
    CACHE_DISABLED = False

from app.utils.validators import validate_url
from app.models.crawler_models import CrawlResult, CrawlConfig

logger = logging.getLogger(__name__)

class SocialMediaCrawlerService:
    """Enhanced crawler service for social media and protected sites"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 30)  # Longer timeout for social media
        self.max_content_length = self.config.get('MAX_CONTENT_LENGTH', 5000)
        
        # More realistic user agents for social media
        self.social_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0'
        ]
        
        # Comprehensive headers to mimic real browsers
        self.realistic_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
        }
        
        # Social media specific configurations
        self.social_domains = {
            'linkedin.com': {
                'wait_time': 5.0,
                'scroll_pause': 2.0,
                'js_enabled': True,
                'wait_for_selector': 'main, .profile-section, .pv-text-details__left-panel'
            },
            'instagram.com': {
                'wait_time': 4.0,
                'scroll_pause': 1.5,
                'js_enabled': True,
                'wait_for_selector': 'article, main, .x1lliihq'
            },
            'twitter.com': {
                'wait_time': 3.0,
                'scroll_pause': 1.0,
                'js_enabled': True,
                'wait_for_selector': '[data-testid="primaryColumn"], [data-testid="UserName"]'
            },
            'x.com': {
                'wait_time': 3.0,
                'scroll_pause': 1.0,
                'js_enabled': True,
                'wait_for_selector': '[data-testid="primaryColumn"], [data-testid="UserName"]'
            },
            'facebook.com': {
                'wait_time': 4.0,
                'scroll_pause': 2.0,
                'js_enabled': True,
                'wait_for_selector': '[data-pagelet="ProfileTilesFeed"], .x1n2onr6'
            }
        }
    
    def get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return ""
    
    def get_social_config(self, url: str) -> Dict:
        """Get social media specific configuration"""
        domain = self.get_domain(url)
        
        # Check for exact domain match
        for social_domain, config in self.social_domains.items():
            if social_domain in domain:
                return config
        
        # Default config for unknown social sites
        return {
            'wait_time': 3.0,
            'scroll_pause': 1.0,
            'js_enabled': True,
            'wait_for_selector': 'main, article, .content'
        }
    
    def is_social_media(self, url: str) -> bool:
        """Check if URL is from a social media platform"""
        domain = self.get_domain(url)
        social_indicators = [
            'linkedin.com', 'instagram.com', 'twitter.com', 'x.com', 
            'facebook.com', 'tiktok.com', 'snapchat.com', 'pinterest.com',
            'youtube.com', 'reddit.com', 'discord.com', 'telegram.org'
        ]
        return any(social in domain for social in social_indicators)
    
    def create_social_browser_config(self, crawl_config: CrawlConfig) -> BrowserConfig:
        """Create browser configuration optimized for social media"""
        return BrowserConfig(
            verbose=crawl_config.verbose,
            headless=True,  # Keep headless but with better stealth
            browser_type="chromium",
            user_agent=random.choice(self.social_user_agents),
            headers=self.realistic_headers,
            viewport_width=1920,
            viewport_height=1080,
            ignore_https_errors=True,
            java_script_enabled=True,  # Enable JavaScript for social media
            accept_downloads=False,
            # Anti-detection arguments (removed problematic --user-data-dir)
            extra_args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-features=TranslateUI',
                '--disable-default-apps',
                '--no-first-run',
                '--no-default-browser-check',
                '--memory-pressure-off',
                '--disable-ipc-flooding-protection',
                '--disable-background-networking',
                '--disable-sync',
                '--disable-features=ImprovedCookieControls',
                # Stealth mode arguments
                '--exclude-switches=enable-automation',
                '--disable-extensions-http-throttling',
                '--aggressive-cache-discard',
                '--disable-infobars',
                '--disable-notifications',
                '--disable-popup-blocking',
            ]
        )
    
    def create_social_run_config(self, crawl_config: CrawlConfig, url: str) -> CrawlerRunConfig:
        """Create run configuration optimized for social media"""
        social_config = self.get_social_config(url)
        
        run_config_params = {
            'word_count_threshold': max(crawl_config.word_count_threshold, 1),
            'excluded_tags': ['script', 'style', 'noscript'],  # Minimal exclusions for social media
            'exclude_external_links': crawl_config.exclude_external_links,
            'process_iframes': False,  # Skip iframes for speed
            'remove_overlay_elements': True,
            'delay_before_return_html': social_config['wait_time'],  # Wait for content to load
            'wait_for': social_config.get('wait_for_selector'),  # Wait for specific elements
            'magic': True,  # Enable magic mode for better content extraction
            'simulate_user': True,  # Simulate user interactions
            'override_navigator': True,  # Override navigator properties
        }
        
        # Add cache mode if available
        if hasattr(CrawlerRunConfig, 'cache_mode'):
            run_config_params['cache_mode'] = CACHE_ENABLED if crawl_config.use_cache else CACHE_DISABLED
        
        return CrawlerRunConfig(**run_config_params)
    
    async def crawl_social_media_url(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Specialized crawling for social media sites"""
        start_time = time.time()
        
        try:
            if not validate_url(url):
                return CrawlResult(
                    success=False,
                    url=url,
                    error="Invalid URL format"
                )
            
            is_social = self.is_social_media(url)
            social_config = self.get_social_config(url)
            
            # Longer delay for social media
            delay = random.uniform(2.0, 4.0) if is_social else random.uniform(0.5, 1.0)
            await asyncio.sleep(delay)
            
            # Create optimized configs
            browser_config = self.create_social_browser_config(crawl_config)
            run_config = self.create_social_run_config(crawl_config, url)
            
            async with AsyncWebCrawler(config=browser_config) as crawler:
                try:
                    # Longer timeout for social media
                    timeout = self.default_timeout if is_social else 15
                    
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=timeout
                    )
                    
                    if result.success:
                        crawl_time = time.time() - start_time
                        return self._process_social_result(result, url, crawl_config.max_content_length, crawl_time, is_social)
                    else:
                        # Try alternative approach for social media
                        if is_social:
                            logger.warning(f"Standard crawl failed for social media URL {url}, trying alternative approach")
                            return await self._try_alternative_social_crawl(url, crawl_config, crawler)
                        else:
                            return CrawlResult(
                                success=False,
                                url=url,
                                error=result.error_message or "Crawl failed"
                            )
                
                except asyncio.TimeoutError:
                    return CrawlResult(
                        success=False,
                        url=url,
                        error=f"Timeout after {timeout}s - Site may require login or have strong bot protection"
                    )
                except Exception as crawl_error:
                    logger.error(f"Crawl execution error for {url}: {str(crawl_error)}")
                    
                    # Special handling for social media errors
                    if is_social:
                        return CrawlResult(
                            success=False,
                            url=url,
                            error=f"Social media crawl failed - Site likely requires login or has anti-bot protection: {str(crawl_error)}"
                        )
                    else:
                        return CrawlResult(
                            success=False,
                            url=url,
                            error=f"Crawl execution failed: {str(crawl_error)}"
                        )

        except Exception as e:
            logger.error(f"Social media crawl setup error for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Setup error: {str(e)}"
            )
    
    async def _try_alternative_social_crawl(self, url: str, crawl_config: CrawlConfig, crawler) -> CrawlResult:
        """Alternative crawling approach for social media"""
        try:
            # Simplified config for alternative attempt
            alt_config = CrawlerRunConfig(
                word_count_threshold=1,
                excluded_tags=[],
                delay_before_return_html=8.0,  # Even longer wait
                magic=False,
                simulate_user=False,
            )
            
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=alt_config),
                timeout=45
            )
            
            if result.success:
                return self._process_social_result(result, url, crawl_config.max_content_length, 0, True)
            else:
                return CrawlResult(
                    success=False,
                    url=url,
                    error="Alternative social media crawl also failed - Content may require authentication"
                )
        
        except Exception as e:
            return CrawlResult(
                success=False,
                url=url,
                error=f"Alternative crawl failed: {str(e)}"
            )
    
    def _process_social_result(self, result, url: str, max_content_length: int = None, crawl_time: float = 0, is_social: bool = False) -> CrawlResult:
        """Process result with social media specific handling"""
        try:
            content_limit = max_content_length or self.max_content_length
            content = result.markdown[:content_limit] if result.markdown else ''
            
            # If content is very short, it might be blocked content
            if is_social and len(content.strip()) < 50:
                content += "\n\n[Note: Limited content retrieved - site may require login or have anti-bot protection]"
            
            # Extract title with fallbacks for social media
            title = ""
            if hasattr(result, 'title') and result.title:
                title = result.title
            elif 'linkedin.com' in url and 'LinkedIn' not in content[:100]:
                title = "LinkedIn Profile (Login Required)"
            elif 'instagram.com' in url and 'Instagram' not in content[:100]:
                title = "Instagram Profile (Login Required)"
            
            return CrawlResult(
                success=True,
                url=url,
                title=title[:200] if title else '',
                content=content,
                word_count=len(content.split()) if content else 0,
                images=[],  # Skip for social media due to complexity
                internal_links=[],
                external_links=[],
                metadata={
                    'crawl_time': round(crawl_time, 2),
                    'status_code': getattr(result, 'status_code', None),
                    'is_social_media': is_social,
                    'content_length': len(content),
                    'note': 'Social media sites may require login for full content access' if is_social else None
                }
            )
        except Exception as e:
            logger.error(f"Error processing social result for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Result processing failed: {str(e)}"
            )

# Enhanced main crawler service
class CrawlerService(SocialMediaCrawlerService):
    """Main crawler service with social media support"""
    
    async def crawl_single_url(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Main crawl method with social media detection"""
        if self.is_social_media(url):
            logger.info(f"Detected social media URL: {url} - Using enhanced social media crawler")
            return await self.crawl_social_media_url(url, crawl_config)
        else:
            # Use the fast crawler for non-social media sites
            return await self.crawl_single_url_fast(url, crawl_config)
    
    async def crawl_single_url_fast(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Fast crawling for non-social media sites"""
        # Your existing fast crawl implementation
        start_time = time.time()
        
        try:
            if not validate_url(url):
                return CrawlResult(success=False, url=url, error="Invalid URL format")
            
            await asyncio.sleep(random.uniform(0.1, 0.5))
            
            browser_config = BrowserConfig(
                verbose=False,
                headless=True,
                browser_type="chromium",
                user_agent=random.choice(self.social_user_agents),
                headers={'Accept': 'text/html,application/xhtml+xml'},
                viewport_width=1280,
                viewport_height=720,
                ignore_https_errors=True,
                java_script_enabled=False,
                accept_downloads=False,
                extra_args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-images']
            )
            
            run_config = CrawlerRunConfig(
                word_count_threshold=crawl_config.word_count_threshold,
                excluded_tags=crawl_config.excluded_tags + ['script', 'style', 'noscript'],
                exclude_external_links=True,
                process_iframes=False,
                remove_overlay_elements=True,
                delay_before_return_html=0.5,
                magic=False,
            )
            
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await asyncio.wait_for(
                    crawler.arun(url=url, config=run_config),
                    timeout=15
                )
                
                if result.success:
                    crawl_time = time.time() - start_time
                    return self._process_social_result(result, url, crawl_config.max_content_length, crawl_time, False)
                else:
                    return CrawlResult(success=False, url=url, error=result.error_message or "Crawl failed")
        
        except Exception as e:
            return CrawlResult(success=False, url=url, error=str(e))
    
    async def crawl_multiple_urls(self, urls: List[str], crawl_config: CrawlConfig) -> List[CrawlResult]:
        """Batch crawling with social media detection"""
        results = []
        for url in urls:
            # Add longer delays for social media in batch processing
            delay = random.uniform(3.0, 6.0) if self.is_social_media(url) else random.uniform(0.5, 1.0)
            await asyncio.sleep(delay)
            
            result = await self.crawl_single_url(url, crawl_config)
            results.append(result)
        
        return results