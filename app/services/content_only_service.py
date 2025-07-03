# app/services/content_only_service.py
import asyncio
import logging
import random
import time
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.extraction_strategy import NoExtractionStrategy
except ImportError:
    from crawl4ai.async_webcrawler import AsyncWebCrawler
    from crawl4ai.extraction_strategy import NoExtractionStrategy

from app.utils.validators import validate_url
from app.models.crawler_models import CrawlResult, CrawlConfig

logger = logging.getLogger(__name__)


class ContentOnlyExtractor:
    """Extract clean text content from HTML without images, links, and unwanted elements"""
    
    def __init__(self):
        # Tags to completely remove
        self.remove_tags = [
            'script', 'style', 'noscript', 'link', 'meta', 'title',
            'nav', 'footer', 'header', 'aside', 'form', 'input', 
            'button', 'select', 'textarea', 'iframe', 'embed',
            'object', 'audio', 'video', 'canvas', 'svg'
        ]
        
        # Tags to remove but keep content
        self.unwrap_tags = ['a', 'img', 'picture', 'figure', 'figcaption']
        
        # Block-level tags that should add line breaks
        self.block_tags = [
            'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'article', 'section', 'main', 'blockquote', 'pre',
            'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'tr', 'td', 'th'
        ]
    
    def clean_html(self, html_content: str) -> str:
        """Clean HTML and extract only text content"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted tags completely
            for tag in soup(self.remove_tags):
                tag.decompose()
            
            # Remove images and links but keep their text content
            for tag in soup.find_all('img'):
                tag.decompose()
            
            for tag in soup.find_all('a'):
                if tag.string:
                    tag.replace_with(tag.get_text())
                else:
                    tag.unwrap()
            
            # Find main content areas (prioritize)
            main_content = None
            content_selectors = [
                'main', 'article', '[role="main"]',
                '.content', '.post-content', '.article-content',
                '.entry-content', '.post-body', '.article-body',
                '#content', '#main-content', '#article-content'
            ]
            
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            # Use main content if found, otherwise use body
            if main_content:
                content_soup = main_content
            else:
                content_soup = soup.find('body') or soup
            
            # Extract text with proper spacing
            text_parts = []
            for element in content_soup.descendants:
                if element.name in self.block_tags and element.get_text(strip=True):
                    text_parts.append(element.get_text(strip=True))
                elif element.string and element.string.strip():
                    parent_tag = element.parent.name if element.parent else None
                    if parent_tag not in self.remove_tags:
                        text_parts.append(element.string.strip())
            
            # Join text parts and clean up
            content = ' '.join(text_parts)
            
            # Clean up extra whitespace
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r'\n\s*\n', '\n\n', content)
            
            return content.strip()
            
        except Exception as e:
            logger.error(f"Error cleaning HTML: {str(e)}")
            # Fallback: simple regex cleaning
            return self._simple_text_extraction(html_content)
    
    def _simple_text_extraction(self, html_content: str) -> str:
        """Fallback simple text extraction using regex"""
        # Remove script and style tags
        content = re.sub(r'<script.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove all HTML tags
        content = re.sub(r'<[^>]+>', ' ', content)
        
        # Clean up whitespace
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\n\s*\n', '\n\n', content)
        
        return content.strip()


class ContentOnlyCrawlerService:
    """Crawler service specialized for content-only extraction"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 15)
        self.max_content_length = self.config.get('MAX_CONTENT_LENGTH', 10000)
        self.extractor = ContentOnlyExtractor()
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
    
    def get_random_delay(self) -> float:
        """Random delay between requests"""
        return random.uniform(0.3, 0.8)
    
    async def crawl_content_only(self, url: str, max_length: Optional[int] = None) -> CrawlResult:
        """Crawl URL and extract only clean text content"""
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
            
            # Configure crawler for content extraction
            crawler_params = {
                'verbose': False,
                'headless': True,
                'user_agent': random.choice(self.user_agents)
            }
            
            # Try to crawl
            try:
                async with AsyncWebCrawler(**crawler_params) as crawler:
                    result = await asyncio.wait_for(
                        crawler.arun(
                            url=url,
                            word_count_threshold=5,  # Lower threshold for content
                            extraction_strategy=NoExtractionStrategy(),
                            bypass_cache=False,
                            delay_before_return_html=1.0  # Ensure page loads
                        ),
                        timeout=self.default_timeout
                    )
                    
                    return self._process_content_result(result, url, max_length, time.time() - start_time)
                    
            except TypeError:
                # Fallback for older API
                crawler = AsyncWebCrawler(**crawler_params)
                result = await asyncio.wait_for(
                    crawler.arun(url=url) if hasattr(crawler, 'arun') else asyncio.to_thread(crawler.run, url),
                    timeout=self.default_timeout
                )
                
                return self._process_content_result(result, url, max_length, time.time() - start_time)
                
        except asyncio.TimeoutError:
            return CrawlResult(
                success=False,
                url=url,
                error=f"Content extraction timeout after {self.default_timeout}s"
            )
        except Exception as e:
            logger.error(f"Content crawl error for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Content extraction failed: {str(e)}"
            )
    
    def _process_content_result(self, result: Any, url: str, max_length: Optional[int], crawl_time: float) -> CrawlResult:
        """Process crawl result and extract clean content"""
        try:
            # Check if crawl was successful
            if hasattr(result, 'success') and not result.success:
                return CrawlResult(
                    success=False,
                    url=url,
                    error=getattr(result, 'error_message', 'Content extraction failed')
                )
            
            # Get HTML content
            html_content = ''
            if hasattr(result, 'html'):
                html_content = result.html
            elif hasattr(result, 'cleaned_html'):
                html_content = result.cleaned_html
            else:
                return CrawlResult(
                    success=False,
                    url=url,
                    error="No HTML content found"
                )
            
            # Extract clean text content
            clean_content = self.extractor.clean_html(html_content)
            
            # Apply length limit
            content_length = max_length or self.max_content_length
            if len(clean_content) > content_length:
                clean_content = clean_content[:content_length] + "..."
            
            # Extract title
            title = ''
            if hasattr(result, 'title'):
                title = result.title
            else:
                # Try to extract title from HTML
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.get_text().strip()
                except:
                    title = ''
            
            return CrawlResult(
                success=True,
                url=url,
                title=title[:200] if title else '',
                content=clean_content,
                word_count=len(clean_content.split()) if clean_content else 0,
                images=[],  # No images in content-only mode
                internal_links=[],  # No links in content-only mode
                external_links=[],  # No links in content-only mode
                metadata={
                    'crawl_time': round(crawl_time, 2),
                    'status_code': getattr(result, 'status_code', 200),
                    'content_length': len(clean_content),
                    'original_html_length': len(html_content),
                    'extraction_mode': 'content_only',
                    'images_removed': True,
                    'links_removed': True
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing content result: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Content processing failed: {str(e)}"
            )
    
    async def crawl_multiple_content_only(self, urls: List[str], max_length: Optional[int] = None, max_concurrent: int = 3) -> List[CrawlResult]:
        """Crawl multiple URLs for content-only extraction"""
        max_concurrent = min(max_concurrent, 5)  # Safety limit
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_limit(url):
            async with semaphore:
                return await self.crawl_content_only(url, max_length)
        
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
                        error=f"Content extraction failed: {str(result)}"
                    ))
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Batch content crawl error: {str(e)}")
            return [CrawlResult(success=False, url=url, error="Batch content extraction failed") for url in urls]