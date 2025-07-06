# app/services/array_content_service.py - FIXED VERSION
import asyncio
import logging
import random
import time
import re
from typing import Dict, List, Optional, Any, Union
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


class ArrayContentExtractor:
    """Extract content as arrays for repeated elements with deduplication"""
    
    def __init__(self):
        # Tags to completely remove
        self.remove_tags = [
            'script', 'style', 'noscript', 'link', 'meta',
            'form', 'input', 'button', 'select', 'textarea'
        ]
        
        # Tags that typically contain unwanted content
        self.unwrap_tags = ['a', 'img', 'picture', 'figure', 'figcaption']
        
        # Block-level tags for text extraction
        self.block_tags = [
            'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'article', 'section', 'main', 'blockquote', 'pre',
            'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'tr', 'td', 'th'
        ]
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0
        return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def _is_duplicate_content(self, content: str, existing_contents: List[str], threshold: float = 0.85) -> bool:
        """Check if content is duplicate of existing content"""
        if not content.strip() or len(content.strip()) < 20:
            return True
        
        normalized_content = re.sub(r'\s+', ' ', content.strip().lower())
        
        for existing in existing_contents:
            if not existing.strip():
                continue
                
            normalized_existing = re.sub(r'\s+', ' ', existing.strip().lower())
            
            # Check exact match
            if normalized_content == normalized_existing:
                return True
            
            # Check similarity ratio
            similarity = self._calculate_similarity(normalized_content, normalized_existing)
            if similarity > threshold:
                return True
        
        return False
    
    def _deduplicate_sentences(self, text: str) -> str:
        """Remove duplicate sentences within text"""
        if not text or len(text) < 50:
            return text
        
        # Split into sentences
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if char in '.!?' and len(current_sentence.strip()) > 15:
                sentence = current_sentence.strip()
                if sentence:
                    # Check for duplicates
                    normalized = re.sub(r'\s+', ' ', sentence.lower())
                    if not any(self._calculate_similarity(normalized, re.sub(r'\s+', ' ', s.lower())) > 0.8 
                             for s in sentences):
                        sentences.append(sentence)
                current_sentence = ""
        
        # Add remaining text if any
        if current_sentence.strip():
            remaining = current_sentence.strip()
            normalized = re.sub(r'\s+', ' ', remaining.lower())
            if not any(self._calculate_similarity(normalized, re.sub(r'\s+', ' ', s.lower())) > 0.8 
                     for s in sentences):
                sentences.append(remaining)
        
        return ' '.join(sentences)
    
    def _remove_duplicate_array_items(self, items: List[Dict]) -> List[Dict]:
        """Remove duplicate items from array based on main_content"""
        if not items or len(items) <= 1:
            return items
        
        unique_items = []
        seen_contents = []
        
        for item in items:
            main_content = item.get('main_content', '').strip()
            
            if not main_content or len(main_content) < 20:
                continue
            
            # Check if this item is duplicate
            if not self._is_duplicate_content(main_content, seen_contents, threshold=0.75):
                unique_items.append(item)
                seen_contents.append(main_content)
            else:
                logger.debug(f"Removed duplicate array item: {main_content[:50]}...")
        
        return unique_items
    
    def extract_array_content(self, html_content: str, 
                            array_selectors: Dict[str, Any], 
                            exclude_selectors: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Extract content as arrays for repeated elements with deduplication
        
        Args:
            html_content: Raw HTML content
            array_selectors: Dict with selector configs
            exclude_selectors: List of CSS selectors to exclude
            
        Returns:
            Dict with extracted arrays and metadata (deduplicated)
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted tags completely
            for tag in soup(self.remove_tags):
                tag.decompose()
            
            # Remove excluded selectors if specified
            if exclude_selectors:
                for selector in exclude_selectors:
                    try:
                        for element in soup.select(selector):
                            element.decompose()
                    except Exception as e:
                        logger.warning(f"Invalid exclude selector '{selector}': {str(e)}")
            
            extracted_arrays = {}
            total_items = 0
            
            # Process each array selector
            for selector_name, selector_config in array_selectors.items():
                try:
                    # Handle both string selectors and config objects
                    if isinstance(selector_config, str):
                        selector = selector_config
                        sub_selectors = {}
                        limit = None
                    else:
                        selector = selector_config.get('selector', '')
                        sub_selectors = selector_config.get('sub_selectors', {})
                        limit = selector_config.get('limit', None)
                    
                    if not selector:
                        continue
                    
                    # Find all matching elements
                    elements = soup.select(selector)
                    
                    if limit and len(elements) > limit:
                        elements = elements[:limit]
                    
                    array_items = []
                    
                    for i, element in enumerate(elements):
                        # Extract main content with deduplication
                        main_content = self._extract_text_from_element(element)
                        main_content = self._deduplicate_sentences(main_content)
                        
                        if not main_content or len(main_content.strip()) < 15:
                            continue
                        
                        item_data = {
                            'index': i,
                            'main_content': main_content
                        }
                        
                        # Extract sub-selectors if specified
                        if sub_selectors:
                            for sub_name, sub_selector in sub_selectors.items():
                                try:
                                    sub_elements = element.select(sub_selector)
                                    if sub_elements:
                                        if len(sub_elements) == 1:
                                            # Single element - extract as string with deduplication
                                            sub_content = self._extract_text_from_element(sub_elements[0])
                                            sub_content = self._deduplicate_sentences(sub_content)
                                            item_data[sub_name] = sub_content
                                        else:
                                            # Multiple elements - extract as array with deduplication
                                            sub_contents = []
                                            for sub_el in sub_elements:
                                                sub_content = self._extract_text_from_element(sub_el)
                                                sub_content = self._deduplicate_sentences(sub_content)
                                                if sub_content and sub_content not in sub_contents:
                                                    sub_contents.append(sub_content)
                                            item_data[sub_name] = sub_contents
                                    else:
                                        item_data[sub_name] = ""
                                except Exception as e:
                                    logger.warning(f"Error extracting sub-selector '{sub_name}': {str(e)}")
                                    item_data[sub_name] = ""
                        
                        # Add metadata
                        item_data['word_count'] = len(item_data['main_content'].split()) if item_data['main_content'] else 0
                        item_data['char_count'] = len(item_data['main_content']) if item_data['main_content'] else 0
                        
                        array_items.append(item_data)
                    
                    # Remove duplicate items from the array
                    array_items = self._remove_duplicate_array_items(array_items)
                    
                    # Update indices after deduplication
                    for i, item in enumerate(array_items):
                        item['index'] = i
                    
                    extracted_arrays[selector_name] = {
                        'selector': selector,
                        'items': array_items,
                        'count': len(array_items),
                        'sub_selectors_used': list(sub_selectors.keys()) if sub_selectors else [],
                        'deduplication_applied': len(array_items) < len(elements) if elements else False
                    }
                    
                    total_items += len(array_items)
                    
                    logger.info(f"Selector '{selector_name}': {len(elements)} elements found, {len(array_items)} unique items after deduplication")
                    
                except Exception as e:
                    logger.error(f"Error processing selector '{selector_name}': {str(e)}")
                    extracted_arrays[selector_name] = {
                        'selector': selector_config,
                        'items': [],
                        'count': 0,
                        'error': str(e)
                    }
            
            return {
                'arrays': extracted_arrays,
                'metadata': {
                    'total_selectors': len(array_selectors),
                    'total_items_extracted': total_items,
                    'extraction_method': 'array_based_deduplicated',
                    'successful_selectors': [
                        name for name, data in extracted_arrays.items() 
                        if data['count'] > 0
                    ],
                    'deduplication_stats': {
                        'total_arrays': len(extracted_arrays),
                        'deduplication_applied': any(
                            data.get('deduplication_applied', False) 
                            for data in extracted_arrays.values()
                        )
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error in array content extraction: {str(e)}")
            return {
                'arrays': {},
                'metadata': {
                    'extraction_method': 'array_based_failed',
                    'error': str(e)
                }
            }
    
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
            if alt_text and len(alt_text) > 3:
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
        
        return text.strip()


class ArrayBasedCrawlerService:
    """Crawler service for array-based content extraction with deduplication"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.default_timeout = self.config.get('CRAWLER_TIMEOUT', 20)
        self.extractor = ArrayContentExtractor()
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
    
    def get_random_delay(self) -> float:
        """Random delay between requests"""
        return random.uniform(0.3, 0.8)
    
    async def crawl_array_content(self, url: str, 
                                array_selectors: Dict[str, Any],
                                exclude_selectors: Optional[List[str]] = None,
                                format_output: str = 'structured') -> CrawlResult:
        """
        Crawl URL and extract content as arrays with deduplication
        
        Args:
            url: URL to crawl
            array_selectors: Dict of selectors to extract as arrays
            exclude_selectors: List of CSS selectors to exclude
            format_output: 'structured', 'flat', or 'summary'
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
            
            # Validate array selectors
            if not array_selectors or not isinstance(array_selectors, dict):
                return CrawlResult(
                    success=False,
                    url=url,
                    error="array_selectors must be a non-empty dictionary"
                )
            
            if len(array_selectors) > 5:  # Limit number of array selectors
                return CrawlResult(
                    success=False,
                    url=url,
                    error="Maximum 5 array selectors allowed"
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
                            word_count_threshold=1,
                            extraction_strategy=NoExtractionStrategy(),
                            bypass_cache=False,
                            delay_before_return_html=1.5
                        ),
                        timeout=self.default_timeout
                    )
                    
                    return self._process_array_result(
                        result, url, array_selectors, exclude_selectors, 
                        format_output, time.time() - start_time
                    )
                    
            except TypeError:
                # Fallback for older API
                crawler = AsyncWebCrawler(**crawler_params)
                result = await asyncio.wait_for(
                    crawler.arun(url=url) if hasattr(crawler, 'arun') else asyncio.to_thread(crawler.run, url),
                    timeout=self.default_timeout
                )
                
                return self._process_array_result(
                    result, url, array_selectors, exclude_selectors, 
                    format_output, time.time() - start_time
                )
                
        except asyncio.TimeoutError:
            return CrawlResult(
                success=False,
                url=url,
                error=f"Array content extraction timeout after {self.default_timeout}s"
            )
        except Exception as e:
            logger.error(f"Array content crawl error for {url}: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Array content extraction failed: {str(e)}"
            )
    
    def _process_array_result(self, result: Any, url: str, 
                            array_selectors: Dict[str, Any],
                            exclude_selectors: Optional[List[str]],
                            format_output: str,
                            crawl_time: float) -> CrawlResult:
        """Process crawl result for array extraction with deduplication"""
        try:
            # Check if crawl was successful
            if hasattr(result, 'success') and not result.success:
                return CrawlResult(
                    success=False,
                    url=url,
                    error=getattr(result, 'error_message', 'Array content extraction failed')
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
            
            # Extract array content with deduplication
            extraction_result = self.extractor.extract_array_content(
                html_content, array_selectors, exclude_selectors
            )
            
            arrays = extraction_result["arrays"]
            extraction_metadata = extraction_result["metadata"]
            
            # Format output based on preference
            content = self._format_array_output(arrays, format_output)
            
            # Extract title
            title = ''
            if hasattr(result, 'title'):
                title = result.title
            else:
                try:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.get_text().strip()
                except:
                    title = ''
            
            # Calculate total word count from unique items only
            total_words = sum(
                sum(item.get('word_count', 0) for item in data.get('items', []))
                for data in arrays.values()
            )
            
            # Prepare metadata with deduplication info
            metadata = {
                'crawl_time': round(crawl_time, 2),
                'status_code': getattr(result, 'status_code', 200),
                'original_html_length': len(html_content),
                'extraction_mode': 'array_based_deduplicated',
                'array_selectors_used': list(array_selectors.keys()),
                'exclude_selectors_used': exclude_selectors or [],
                'format_output': format_output,
                'arrays': arrays,  # Full array data with deduplication info
                'content_quality': {
                    'total_unique_items': sum(data['count'] for data in arrays.values()),
                    'deduplication_applied': extraction_metadata.get('deduplication_stats', {}).get('deduplication_applied', False),
                    'arrays_with_deduplication': [
                        name for name, data in arrays.items() 
                        if data.get('deduplication_applied', False)
                    ]
                },
                **extraction_metadata
            }
            
            return CrawlResult(
                success=True,
                url=url,
                title=title[:200] if title else '',
                content=content,
                word_count=total_words,
                images=[],
                internal_links=[],
                external_links=[],
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Error processing array result: {str(e)}")
            return CrawlResult(
                success=False,
                url=url,
                error=f"Array processing failed: {str(e)}"
            )
    
    def _format_array_output(self, arrays: Dict[str, Any], format_type: str) -> str:
        """Format array output based on type with deduplication awareness"""
        if format_type == 'structured':
            # Return structured format with clear sections and deduplication info
            output_parts = []
            for selector_name, data in arrays.items():
                items = data.get('items', [])
                if items:
                    dedup_info = " (deduplicated)" if data.get('deduplication_applied', False) else ""
                    output_parts.append(f"=== {selector_name.upper()} ({data['count']} unique items{dedup_info}) ===")
                    
                    for i, item in enumerate(items, 1):
                        item_text = f"\n[Item {i}]\n{item['main_content']}"
                        
                        # Add sub-selector data if available
                        for key, value in item.items():
                            if key not in ['index', 'main_content', 'word_count', 'char_count']:
                                if isinstance(value, list):
                                    if value:  # Only show non-empty lists
                                        item_text += f"\n{key}: {' | '.join(str(v) for v in value if v)}"
                                elif value:
                                    item_text += f"\n{key}: {value}"
                        
                        output_parts.append(item_text)
                    output_parts.append("")  # Add spacing
            
            return "\n".join(output_parts)
        
        elif format_type == 'flat':
            # Return flat list of all unique items
            all_items = []
            for data in arrays.values():
                for item in data.get('items', []):
                    if item['main_content'] and item['main_content'] not in all_items:
                        all_items.append(item['main_content'])
            return "\n\n".join(all_items)
        
        elif format_type == 'summary':
            # Return summary with counts and deduplication info
            summary_parts = []
            for selector_name, data in arrays.items():
                count = data['count']
                selector = data['selector']
                dedup_note = " (after deduplication)" if data.get('deduplication_applied', False) else ""
                summary_parts.append(f"{selector_name}: {count} unique items{dedup_note} found with selector '{selector}'")
            return "\n".join(summary_parts)
        
        else:
            # Default to structured
            return self._format_array_output(arrays, 'structured')
    
    async def crawl_multiple_array_content(self, urls: List[str], 
                                         array_selectors: Dict[str, Any],
                                         exclude_selectors: Optional[List[str]] = None,
                                         format_output: str = 'structured',
                                         max_concurrent: int = 2) -> List[CrawlResult]:
        """Crawl multiple URLs for array content with deduplication"""
        max_concurrent = min(max_concurrent, 3)  # Conservative limit
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_limit(url):
            async with semaphore:
                return await self.crawl_array_content(
                    url, array_selectors, exclude_selectors, format_output
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
                        error=f"Array content extraction failed: {str(result)}"
                    ))
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Batch array content crawl error: {str(e)}")
            return [CrawlResult(success=False, url=url, error="Batch array extraction failed") for url in urls]