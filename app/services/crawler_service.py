import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

# Import from crawl4ai - adjust based on actual API
try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.extraction_strategy import NoExtractionStrategy
except ImportError:
    # Fallback imports for different versions
    from crawl4ai.async_webcrawler import AsyncWebCrawler
    from crawl4ai.extraction_strategy import NoExtractionStrategy

from app.utils.validators import validate_url
from app.models.crawler_models import CrawlResult, CrawlConfig

logger = logging.getLogger(__name__)


class SimpleCrawlerService:
    """Simplified crawler service that works with various crawl4ai versions"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 15)
        self.max_content_length = self.config.get('MAX_CONTENT_LENGTH', 5000)
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
    
    def get_random_delay(self) -> float:
        """Random delay between requests"""
        return random.uniform(0.5, 1.5)
    
    async def crawl_url_simple(self, url: str, config: CrawlConfig) -> CrawlResult:
        """Simple crawl implementation"""
        start_time = time.time()
        
        try:
            # Validate URL
            if not validate_url(url):
                return CrawlResult(
                    success=False,
                    url=url,
                    error="Invalid URL format"
                )
            
            # Add delay
            await asyncio.sleep(self.get_random_delay())
            
            # Try the simplest approach first
            crawler_params = {
                'verbose': False,
                'headless': True,
            }
            
            # Create and use crawler
            try:
                # Try context manager approach first (newer API)
                async with AsyncWebCrawler(**crawler_params) as crawler:
                    result = await asyncio.wait_for(
                        crawler.arun(
                            url=url,
                            word_count_threshold=config.word_count_threshold,
                            extraction_strategy=NoExtractionStrategy(),
                            bypass_cache=not config.use_cache
                        ),
                        timeout=self.default_timeout
                    )
                    
                    return self._process_result(result, url, config, time.time() - start_time)
                    
            except TypeError:
                # Fallback: Try without context manager (older API)
                crawler = AsyncWebCrawler(**crawler_params)
                
                # Check if crawler has async methods
                if hasattr(crawler, 'arun'):
                    result = await asyncio.wait_for(
                        crawler.arun(url=url),
                        timeout=self.default_timeout
                    )
                else:
                    # Synchronous fallback
                    result = await asyncio.wait_for(
                        asyncio.to_thread(crawler.run, url),
                        timeout=self.default_timeout
                    )
                
                return self._process_result(result, url, config, time.time() - start_time)
                
        except asyncio.TimeoutError:
            return CrawlResult(
                success=False,
                url=url,
                error=f"Timeout after {self.default_timeout}s"
            )
        except Exception as e:
            logger.error(f"Crawl error for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Crawl failed: {str(e)}"
            )
    
    def _process_result(self, result: Any, url: str, config: CrawlConfig, crawl_time: float) -> CrawlResult:
        """Process crawl result"""
        try:
            # Handle different result formats
            if hasattr(result, 'success') and not result.success:
                return CrawlResult(
                    success=False,
                    url=url,
                    error=getattr(result, 'error_message', 'Crawl failed')
                )
            
            # Extract content
            content = ''
            if hasattr(result, 'markdown'):
                content = result.markdown
            elif hasattr(result, 'text'):
                content = result.text
            elif hasattr(result, 'html'):
                # Basic HTML to text conversion
                import re
                content = re.sub(r'<[^>]+>', '', result.html)
            
            # Limit content length
            if config.max_content_length and len(content) > config.max_content_length:
                content = content[:config.max_content_length]
            
            return CrawlResult(
                success=True,
                url=url,
                title=getattr(result, 'title', '')[:200] if hasattr(result, 'title') else '',
                content=content,
                word_count=len(content.split()) if content else 0,
                images=[],  # Simplified - no image extraction
                internal_links=[],
                external_links=[],
                metadata={
                    'crawl_time': round(crawl_time, 2),
                    'status_code': getattr(result, 'status_code', 200),
                    'content_length': len(content)
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing result: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Result processing failed: {str(e)}"
            )
    
    async def crawl_multiple_urls(self, urls: List[str], config: CrawlConfig) -> List[CrawlResult]:
        """Crawl multiple URLs with concurrency control"""
        max_concurrent = min(getattr(config, 'max_concurrent', 3), 3)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_limit(url):
            async with semaphore:
                return await self.crawl_url_simple(url, config)
        
        tasks = [crawl_with_limit(url) for url in urls]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append(CrawlResult(
                        success=False,
                        url=urls[i] if i < len(urls) else "unknown",
                        error=f"Task failed: {str(result)}"
                    ))
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Batch crawl error: {str(e)}")
            return [CrawlResult(success=False, url=url, error="Batch failed") for url in urls]


# Main service classes
class HighSpeedCrawlerService(SimpleCrawlerService):
    """High-speed crawler using simplified approach"""
    
    async def crawl_single_url_fast(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Fast single URL crawling"""
        return await self.crawl_url_simple(url, crawl_config)
    
    async def crawl_multiple_urls_concurrent(self, urls: List[str], crawl_config: CrawlConfig, max_concurrent: int = 3) -> List[CrawlResult]:
        """Concurrent crawling"""
        return await self.crawl_multiple_urls(urls, crawl_config)


class CrawlerService(HighSpeedCrawlerService):
    """Main crawler service with compatibility"""
    
    async def crawl_single_url(self, url: str, crawl_config: CrawlConfig) -> CrawlResult:
        """Main crawl method"""
        return await self.crawl_single_url_fast(url, crawl_config)
    
    async def crawl_multiple_urls(self, urls: List[str], crawl_config: CrawlConfig) -> List[CrawlResult]:
        """Main batch crawl method"""
        return await self.crawl_multiple_urls_concurrent(urls, crawl_config, 
                                                       getattr(crawl_config, 'max_concurrent', 3))