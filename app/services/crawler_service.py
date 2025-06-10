import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
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

class HighSpeedCrawlerService:
    """Ultra-fast crawler service with improved browser management"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 15)
        self.max_content_length = self.config.get('MAX_CONTENT_LENGTH', 5000)
        
        # Minimal, fast user agents
        self.fast_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]
        
        # Minimal headers for speed
        self.minimal_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
    def get_fast_delay(self) -> float:
        """Very short random delay (0.1-0.5 seconds)"""
        return random.uniform(0.1, 0.5)
    
    def get_fast_user_agent(self) -> str:
        """Get minimal user agent"""
        return random.choice(self.fast_user_agents)
    
    def create_optimized_browser_config(self, crawl_config: CrawlConfig) -> BrowserConfig:
        """Create optimized browser configuration"""
        return BrowserConfig(
            verbose=False,  # Disable verbose logging for speed
            headless=True,  # Always headless for speed
            browser_type="chromium",
            user_agent=self.get_fast_user_agent(),
            headers=self.minimal_headers,
            viewport_width=1280,
            viewport_height=720,
            ignore_https_errors=True,
            java_script_enabled=False,  # Disable JS for speed
            accept_downloads=False,
            extra_args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',  # Don't load images
                '--disable-javascript',  # No JavaScript
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
            ]
        )
    
    def create_optimized_run_config(self, crawl_config: CrawlConfig) -> CrawlerRunConfig:
        """Create optimized crawling configuration"""
        run_config_params = {
            'word_count_threshold': crawl_config.word_count_threshold,
            'excluded_tags': crawl_config.excluded_tags + [
                'script', 'style', 'noscript', 'iframe', 'embed', 'object',
                'video', 'audio', 'canvas', 'svg', 'math'
            ],
            'exclude_external_links': True,
            'process_iframes': False,
            'remove_overlay_elements': True,
            'delay_before_return_html': 0.2,  # Very minimal delay
            'wait_for': None,
            'magic': False,  # Disable magic mode for speed
        }
        
        # Add cache mode if available
        if hasattr(CrawlerRunConfig, 'cache_mode'):
            run_config_params['cache_mode'] = CACHE_ENABLED if crawl_config.use_cache else CACHE_DISABLED
        
        return CrawlerRunConfig(**run_config_params)
        
    async def crawl_single_url_fast(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Ultra-fast single URL crawling with proper browser management"""
        start_time = time.time()
        
        try:
            # Quick URL validation
            if not validate_url(url):
                return CrawlResult(
                    success=False,
                    url=url,
                    error="Invalid URL format"
                )
            
            # Very short delay
            await asyncio.sleep(self.get_fast_delay())
            
            # Create fresh browser config for each request to avoid issues
            browser_config = self.create_optimized_browser_config(crawl_config)
            run_config = self.create_optimized_run_config(crawl_config)

            # Use context manager to ensure proper cleanup
            async with AsyncWebCrawler(config=browser_config) as crawler:
                try:
                    # Single attempt with timeout
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=self.default_timeout
                    )
                    
                    if result.success:
                        crawl_time = time.time() - start_time
                        return self._process_fast_result(result, url, crawl_config.max_content_length, crawl_time)
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
                        error=f"Timeout after {self.default_timeout}s"
                    )
                except Exception as crawl_error:
                    logger.error(f"Crawl execution error for {url}: {str(crawl_error)}")
                    return CrawlResult(
                        success=False,
                        url=url,
                        error=f"Crawl execution failed: {str(crawl_error)}"
                    )

        except Exception as e:
            logger.error(f"Fast crawl setup error for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Setup error: {str(e)}"
            )
    
    def _process_fast_result(self, result, url: str, max_content_length: int = None, crawl_time: float = 0) -> CrawlResult:
        """Fast result processing - minimal data extraction"""
        try:
            content_limit = max_content_length or self.max_content_length
            content = result.markdown[:content_limit] if result.markdown else ''
            
            # Skip heavy processing for speed - just get essentials
            return CrawlResult(
                success=True,
                url=url,
                title=getattr(result, 'title', '')[:200] if hasattr(result, 'title') else '',
                content=content,
                word_count=len(content.split()) if content else 0,
                images=[],  # Skip image processing for speed
                internal_links=[],  # Skip link processing for speed
                external_links=[],
                metadata={
                    'crawl_time': round(crawl_time, 2),
                    'status_code': getattr(result, 'status_code', None),
                    'speed_mode': 'fast',
                    'content_length': len(content)
                }
            )
        except Exception as e:
            logger.error(f"Error processing result for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Result processing failed: {str(e)}"
            )
    
    async def crawl_multiple_urls_concurrent(self, urls: List[str], crawl_config: CrawlConfig, max_concurrent: int = 3) -> List[CrawlResult]:
        """Concurrent crawling with limited concurrency"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_semaphore(url):
            async with semaphore:
                # Add small delay between concurrent requests
                await asyncio.sleep(random.uniform(0.1, 0.3))
                return await self.crawl_single_url_fast(url, crawl_config)
        
        # Create tasks for all URLs
        tasks = [crawl_with_semaphore(url) for url in urls]
        
        # Execute all tasks concurrently with error handling
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Batch crawl error: {str(e)}")
            return [CrawlResult(success=False, url=url, error="Batch processing failed") for url in urls]
        
        # Handle exceptions in results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(CrawlResult(
                    success=False,
                    url=urls[i] if i < len(urls) else "unknown",
                    error=f"Exception: {str(result)}"
                ))
            else:
                processed_results.append(result)
        
        return processed_results

# Legacy service wrapper for compatibility
class CrawlerService(HighSpeedCrawlerService):
    """Backward compatible crawler service"""
    
    async def crawl_single_url(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Main crawl method - always use fast mode for reliability"""
        return await self.crawl_single_url_fast(url, crawl_config)
    
    async def crawl_multiple_urls(self, urls: List[str], crawl_config: CrawlConfig) -> List[CrawlResult]:
        """Main batch crawl method"""
        max_concurrent = getattr(crawl_config, 'max_concurrent', 3)
        # Limit concurrent requests to prevent browser issues
        safe_concurrent = min(max_concurrent, 3)
        
        return await self.crawl_multiple_urls_concurrent(urls, crawl_config, safe_concurrent)