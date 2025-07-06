import asyncio
import logging
import random
import time
import re
from typing import Dict, List, Optional, Any, Union, Set
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import difflib

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.extraction_strategy import NoExtractionStrategy
except ImportError:
    from crawl4ai.async_webcrawler import AsyncWebCrawler
    from crawl4ai.extraction_strategy import NoExtractionStrategy

from app.utils.validators import validate_url
from app.models.crawler_models import CrawlResult, CrawlConfig

logger = logging.getLogger(__name__)


class EnhancedContentExtractor:
    """Extract clean text content from HTML with custom selector support and deduplication"""
    
    def __init__(self):
        # Default tags to completely remove
        self.remove_tags = [
            'script', 'style', 'noscript', 'link', 'meta', 'title',
            'nav', 'footer', 'header', 'aside', 'form', 'input', 
            'button', 'select', 'textarea', 'iframe', 'embed',
            'object', 'audio', 'video', 'canvas', 'svg'
        ]
        
        # Default tags to remove but keep content
        self.unwrap_tags = ['a', 'img', 'picture', 'figure', 'figcaption']
        
        # Block-level tags that should add line breaks
        self.block_tags = [
            'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'article', 'section', 'main', 'blockquote', 'pre',
            'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'tr', 'td', 'th'
        ]
        
        # Default content selectors (fallback)
        self.default_selectors = [
            'main', 'article', '[role="main"]',
            '.content', '.post-content', '.article-content',
            '.entry-content', '.post-body', '.article-body',
            '#content', '#main-content', '#article-content'
        ]
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0
        
        # Use difflib to calculate similarity ratio
        return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def _is_content_duplicate(self, content: str, existing_contents: List[str], threshold: float = 0.85) -> bool:
        """Check if content is duplicate of existing content"""
        if not content.strip():
            return True
        
        # Normalize content for comparison
        normalized_content = re.sub(r'\s+', ' ', content.strip().lower())
        
        for existing in existing_contents:
            if not existing.strip():
                continue
                
            normalized_existing = re.sub(r'\s+', ' ', existing.strip().lower())
            
            # Check exact match
            if normalized_content == normalized_existing:
                return True
            
            # Check if one is contained in the other (for nested elements)
            if (normalized_content in normalized_existing and 
                len(normalized_content) > len(normalized_existing) * 0.5):
                return True
            
            if (normalized_existing in normalized_content and 
                len(normalized_existing) > len(normalized_content) * 0.5):
                return True
            
            # Check similarity ratio
            similarity = self._calculate_similarity(normalized_content, normalized_existing)
            if similarity > threshold:
                return True
        
        return False
    
    def _remove_nested_content(self, extracted_sections: Dict[str, Dict]) -> Dict[str, Dict]:
        """Remove content that is nested within other extracted content"""
        # Sort sections by content length (longest first)
        sections_by_length = sorted(
            extracted_sections.items(), 
            key=lambda x: len(x[1]['content']), 
            reverse=True
        )
        
        filtered_sections = {}
        used_contents = []
        
        for section_key, section_data in sections_by_length:
            content = section_data['content']
            
            # Check if this content is already covered by a larger section
            if not self._is_content_duplicate(content, used_contents, threshold=0.75):
                filtered_sections[section_key] = section_data
                used_contents.append(content)
            else:
                logger.info(f"Removed duplicate/nested content from selector: {section_data['selector']}")
        
        return filtered_sections
    
    def _prioritize_selectors(self, extracted_sections: Dict[str, Dict]) -> Dict[str, Dict]:
        """Prioritize more specific selectors over general ones"""
        # Priority order: ID selectors > class selectors > element selectors
        def get_selector_priority(selector: str) -> int:
            if '#' in selector:  # ID selector
                return 3
            elif '.' in selector:  # Class selector
                return 2
            elif '[' in selector:  # Attribute selector
                return 2
            else:  # Element selector
                return 1
        
        # Sort by priority (highest first), then by content length
        prioritized_sections = sorted(
            extracted_sections.items(),
            key=lambda x: (
                get_selector_priority(x[1]['selector']),
                len(x[1]['content'])
            ),
            reverse=True
        )
        
        return dict(prioritized_sections)
    
    def _deduplicate_content_blocks(self, content: str) -> str:
        """Remove duplicate paragraphs/blocks within content"""
        if not content:
            return content
        
        # First, split by common separators
        blocks = []
        
        # Try splitting by double newlines first
        initial_blocks = [block.strip() for block in content.split('\n\n') if block.strip()]
        
        if len(initial_blocks) <= 1:
            # If no double newlines, try single newlines
            initial_blocks = [block.strip() for block in content.split('\n') if block.strip()]
        
        if len(initial_blocks) <= 1:
            # If still no separation, try sentences
            initial_blocks = [block.strip() for block in content.split('.') if block.strip() and len(block.strip()) > 20]
        
        # Remove duplicates while preserving order
        seen_blocks = set()
        unique_blocks = []
        
        for block in initial_blocks:
            # Normalize block for comparison
            normalized_block = re.sub(r'\s+', ' ', block.lower().strip())
            
            # Skip very short blocks
            if len(normalized_block) < 15:
                continue
            
            # Check for exact duplicates
            if normalized_block not in seen_blocks:
                # Check for substring duplicates (one block contained in another)
                is_duplicate = False
                for existing_block in seen_blocks:
                    # If this block is largely contained in an existing block, skip it
                    if (normalized_block in existing_block and 
                        len(normalized_block) > len(existing_block) * 0.7):
                        is_duplicate = True
                        break
                    # If an existing block is largely contained in this block, remove the existing one
                    elif (existing_block in normalized_block and 
                          len(existing_block) > len(normalized_block) * 0.7):
                        # Remove the shorter block from seen_blocks and unique_blocks
                        if existing_block in seen_blocks:
                            seen_blocks.remove(existing_block)
                        # Find and remove from unique_blocks
                        unique_blocks = [b for b in unique_blocks 
                                       if re.sub(r'\s+', ' ', b.lower().strip()) != existing_block]
                
                if not is_duplicate:
                    unique_blocks.append(block)
                    seen_blocks.add(normalized_block)
        
        # Join blocks back together
        if len(unique_blocks) > 1:
            return '\n\n'.join(unique_blocks)
        else:
            return '\n\n'.join(unique_blocks) if unique_blocks else content
    
    def clean_html_with_selectors(self, html_content: str, custom_selectors: Optional[List[str]] = None, 
                                exclude_selectors: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Clean HTML and extract content using custom selectors with deduplication
        
        Args:
            html_content: Raw HTML content
            custom_selectors: List of CSS selectors to extract content from
            exclude_selectors: List of CSS selectors to exclude from extraction
            
        Returns:
            Dict with extracted content and metadata (deduplicated)
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            original_soup = BeautifulSoup(html_content, 'html.parser')  # Keep original for fallback
            
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
            
            # Remove excluded selectors if specified
            if exclude_selectors:
                for selector in exclude_selectors:
                    try:
                        for element in soup.select(selector):
                            element.decompose()
                    except Exception as e:
                        logger.warning(f"Invalid exclude selector '{selector}': {str(e)}")
            
            # Extract content using custom selectors
            extracted_content = {}
            
            if custom_selectors:
                # Use custom selectors
                for i, selector in enumerate(custom_selectors):
                    try:
                        elements = soup.select(selector)
                        if elements:
                            selector_content = []
                            for element in elements:
                                text = self._extract_text_from_element(element)
                                if text.strip():
                                    selector_content.append(text)
                            
                            if selector_content:
                                combined_selector_content = " ".join(selector_content)
                                extracted_content[f"selector_{i+1}_{selector}"] = {
                                    "selector": selector,
                                    "content": combined_selector_content,
                                    "element_count": len(elements),
                                    "word_count": len(combined_selector_content.split())
                                }
                    except Exception as e:
                        logger.warning(f"Invalid selector '{selector}': {str(e)}")
                        continue
                
                # If no content found with custom selectors, use fallback
                if not extracted_content:
                    logger.info("No content found with custom selectors, using fallback")
                    fallback_content = self._extract_fallback_content(soup)
                    if fallback_content:
                        extracted_content["fallback"] = {
                            "selector": "fallback",
                            "content": fallback_content,
                            "element_count": 1,
                            "word_count": len(fallback_content.split())
                        }
            else:
                # Use default behavior
                fallback_content = self._extract_fallback_content(soup)
                if fallback_content:
                    extracted_content["default"] = {
                        "selector": "default",
                        "content": fallback_content,
                        "element_count": 1,
                        "word_count": len(fallback_content.split())
                    }
            
            # DEDUPLICATION PROCESS
            logger.info(f"Before deduplication: {len(extracted_content)} sections")
            
            # Step 1: Prioritize selectors
            if len(extracted_content) > 1:
                extracted_content = self._prioritize_selectors(extracted_content)
            
            # Step 2: Remove nested/duplicate content
            if len(extracted_content) > 1:
                extracted_content = self._remove_nested_content(extracted_content)
            
            logger.info(f"After deduplication: {len(extracted_content)} sections")
            
            # Combine remaining unique content
            combined_content = ""
            metadata = {
                "selectors_used": list(extracted_content.keys()),
                "total_sections": len(extracted_content),
                "extraction_method": "custom_selectors_deduplicated" if custom_selectors else "default",
                "deduplication_applied": len(custom_selectors or []) > 1 if custom_selectors else False
            }
            
            if extracted_content:
                if len(extracted_content) == 1:
                    # Single section - apply internal deduplication
                    section_data = list(extracted_content.values())[0]
                    combined_content = self._deduplicate_content_blocks(section_data['content'])
                else:
                    # Multiple unique sections - combine with clear separation
                    content_parts = []
                    for section_key, data in extracted_content.items():
                        # Apply deduplication to each section individually
                        deduplicated_section_content = self._deduplicate_content_blocks(data['content'])
                        content_parts.append(f"[{data['selector']}]\n{deduplicated_section_content}")
                    combined_content = '\n\n'.join(content_parts)
                
                # Final deduplication pass for the entire combined content
                combined_content = self._deduplicate_content_blocks(combined_content)
            
            return {
                "content": combined_content.strip(),
                "sections": extracted_content,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Error cleaning HTML with selectors: {str(e)}")
            # Fallback to simple extraction
            return {
                "content": self._simple_text_extraction(html_content),
                "sections": {},
                "metadata": {"extraction_method": "fallback_regex"}
            }
    
    def _extract_fallback_content(self, soup: BeautifulSoup) -> str:
        """Extract content using default selectors"""
        # Try default selectors first
        for selector in self.default_selectors:
            try:
                main_content = soup.select_one(selector)
                if main_content:
                    return self._extract_text_from_element(main_content)
            except:
                continue
        
        # Use body as last resort
        content_soup = soup.find('body') or soup
        return self._extract_text_from_element(content_soup)
    
    def _extract_text_from_element(self, element) -> str:
        """Extract clean text from a BeautifulSoup element without duplication"""
        if not element:
            return ""
        
        # Create a copy to avoid modifying the original
        element_copy = element.__copy__()
        
        # Remove unwanted nested elements
        for tag in element_copy(self.remove_tags):
            tag.decompose()
        
        # Remove images but keep alt text if available
        for img in element_copy.find_all('img'):
            alt_text = img.get('alt', '').strip()
            if alt_text:
                img.replace_with(f"[Image: {alt_text}]")
            else:
                img.decompose()
        
        # Convert links to text but keep link text
        for link in element_copy.find_all('a'):
            link_text = link.get_text(strip=True)
            if link_text:
                link.replace_with(link_text)
            else:
                link.unwrap()
        
        # Get all text content with proper spacing
        text = element_copy.get_text(separator=' ', strip=True)
        
        # Clean up whitespace and normalize
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Remove any remaining duplicate sentences/paragraphs
        text = self._remove_duplicate_sentences(text)
        
        return text.strip()
    
    def _remove_duplicate_sentences(self, text: str) -> str:
        """Remove duplicate sentences within the text"""
        if not text or len(text) < 50:
            return text
        
        # Split into sentences (basic approach)
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if char in '.!?' and len(current_sentence.strip()) > 10:
                sentence = current_sentence.strip()
                if sentence and sentence not in sentences:
                    sentences.append(sentence)
                current_sentence = ""
        
        # Add remaining text if any
        if current_sentence.strip():
            remaining = current_sentence.strip()
            if remaining not in sentences:
                sentences.append(remaining)
        
        return ' '.join(sentences)
    
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


class EnhancedContentOnlyCrawlerService:
    """Enhanced crawler service with custom selector support and deduplication"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 15)
        self.max_content_length = self.config.get('MAX_CONTENT_LENGTH', 10000)
        self.extractor = EnhancedContentExtractor()
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
    
    def get_random_delay(self) -> float:
        """Random delay between requests"""
        return random.uniform(0.3, 0.8)
    
    async def crawl_with_custom_selectors(self, url: str, custom_selectors: Optional[List[str]] = None, 
                                        exclude_selectors: Optional[List[str]] = None,
                                        max_length: Optional[int] = None,
                                        return_sections: bool = False) -> CrawlResult:
        """
        Crawl URL and extract content using custom CSS selectors with deduplication
        
        Args:
            url: URL to crawl
            custom_selectors: List of CSS selectors to extract content from
            exclude_selectors: List of CSS selectors to exclude
            max_length: Maximum content length
            return_sections: Whether to return individual sections in metadata
        """
        start_time = time.time()
        
        try:
            # Validate URL
            if not validate_url(url):
                return CrawlResult(
                    success=False,
                    url=url,
                    error="Invalid URL format"
                )
            
            # Validate selectors
            if custom_selectors:
                if not isinstance(custom_selectors, list):
                    return CrawlResult(
                        success=False,
                        url=url,
                        error="custom_selectors must be a list of CSS selectors"
                    )
                
                if len(custom_selectors) > 10:  # Limit number of selectors
                    return CrawlResult(
                        success=False,
                        url=url,
                        error="Maximum 10 custom selectors allowed"
                    )
            
            # Add delay
            await asyncio.sleep(self.get_random_delay())
            
            # Configure crawler
            crawler_params = {
                'verbose': False,
                'headless': True,
                'user_agent': random.choice(self.user_agents)
            }
            
            # Crawl the URL
            try:
                async with AsyncWebCrawler(**crawler_params) as crawler:
                    result = await asyncio.wait_for(
                        crawler.arun(
                            url=url,
                            word_count_threshold=3,
                            extraction_strategy=NoExtractionStrategy(),
                            bypass_cache=False,
                            delay_before_return_html=1.0
                        ),
                        timeout=self.default_timeout
                    )
                    
                    return self._process_custom_selector_result(
                        result, url, custom_selectors, exclude_selectors, 
                        max_length, return_sections, time.time() - start_time
                    )
                    
            except TypeError:
                # Fallback for older API
                crawler = AsyncWebCrawler(**crawler_params)
                result = await asyncio.wait_for(
                    crawler.arun(url=url) if hasattr(crawler, 'arun') else asyncio.to_thread(crawler.run, url),
                    timeout=self.default_timeout
                )
                
                return self._process_custom_selector_result(
                    result, url, custom_selectors, exclude_selectors, 
                    max_length, return_sections, time.time() - start_time
                )
                
        except asyncio.TimeoutError:
            return CrawlResult(
                success=False,
                url=url,
                error=f"Custom selector extraction timeout after {self.default_timeout}s"
            )
        except Exception as e:
            logger.error(f"Custom selector crawl error for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Custom selector extraction failed: {str(e)}"
            )
    
    def _process_custom_selector_result(self, result: Any, url: str, 
                                      custom_selectors: Optional[List[str]],
                                      exclude_selectors: Optional[List[str]],
                                      max_length: Optional[int], 
                                      return_sections: bool,
                                      crawl_time: float) -> CrawlResult:
        """Process crawl result with custom selectors and deduplication"""
        try:
            # Check if crawl was successful
            if hasattr(result, 'success') and not result.success:
                return CrawlResult(
                    success=False,
                    url=url,
                    error=getattr(result, 'error_message', 'Custom selector extraction failed')
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
            
            # Extract content using custom selectors with deduplication
            extraction_result = self.extractor.clean_html_with_selectors(
                html_content, custom_selectors, exclude_selectors
            )
            
            clean_content = extraction_result["content"]
            sections = extraction_result["sections"]
            extraction_metadata = extraction_result["metadata"]
            
            # Apply length limit
            content_length = max_length or self.max_content_length
            if len(clean_content) > content_length:
                clean_content = clean_content[:content_length] + "..."
            
            # Extract title
            title = ''
            if hasattr(result, 'title'):
                title = result.title
            else:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.get_text().strip()
                except:
                    title = ''
            
            # Prepare metadata
            metadata = {
                'crawl_time': round(crawl_time, 2),
                'status_code': getattr(result, 'status_code', 200),
                'content_length': len(clean_content),
                'original_html_length': len(html_content),
                'extraction_mode': 'custom_selectors_deduplicated',
                'selectors_used': custom_selectors or [],
                'exclude_selectors_used': exclude_selectors or [],
                'deduplication_stats': {
                    'selectors_provided': len(custom_selectors) if custom_selectors else 0,
                    'unique_sections_found': len(sections),
                    'deduplication_applied': extraction_metadata.get('deduplication_applied', False)
                },
                **extraction_metadata
            }
            
            # Add sections to metadata if requested
            if return_sections:
                metadata['sections'] = sections
            
            return CrawlResult(
                success=True,
                url=url,
                title=title[:200] if title else '',
                content=clean_content,
                word_count=len(clean_content.split()) if clean_content else 0,
                images=[],
                internal_links=[],
                external_links=[],
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Error processing custom selector result: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Custom selector processing failed: {str(e)}"
            )
    
    async def crawl_multiple_with_selectors(self, urls: List[str], 
                                          custom_selectors: Optional[List[str]] = None,
                                          exclude_selectors: Optional[List[str]] = None,
                                          max_length: Optional[int] = None,
                                          max_concurrent: int = 3) -> List[CrawlResult]:
        """Crawl multiple URLs with custom selectors and deduplication"""
        max_concurrent = min(max_concurrent, 5)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_limit(url):
            async with semaphore:
                return await self.crawl_with_custom_selectors(
                    url, custom_selectors, exclude_selectors, max_length
                )
        
        tasks = [crawl_with_limit(url) for url in urls]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append(CrawlResult(
                        success=False,
                        url=urls[i] if i < len(urls) else "unknown",
                        error=f"Custom selector extraction failed: {str(result)}"
                    ))
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Batch custom selector crawl error: {str(e)}")
            return [CrawlResult(success=False, url=url, error="Batch custom selector extraction failed") for url in urls]