from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class CrawlConfig:
    """Configuration for crawling operations with speed optimizations"""
    word_count_threshold: int = 10
    excluded_tags: List[str] = field(default_factory=lambda: ['form', 'header', 'nav', 'footer'])
    exclude_external_links: bool = True
    process_iframes: bool = True
    remove_overlay_elements: bool = True
    use_cache: bool = True
    verbose: bool = False
    headless: bool = True
    max_content_length: int = 5000
    
    # Speed optimization options
    speed_mode: str = 'fast'  # 'fast' or 'normal'
    max_concurrent: int = 3  # For batch requests
    skip_images: bool = True  # Skip image processing for speed
    skip_links: bool = False  # Skip link processing for speed
    minimal_processing: bool = False  # Minimal data extraction

@dataclass
class CrawlResult:
    """Result of a crawling operation"""
    success: bool
    url: str
    title: str = ""
    content: str = ""
    word_count: int = 0
    images: List[Dict[str, str]] = field(default_factory=list)
    internal_links: List[Dict[str, str]] = field(default_factory=list)
    external_links: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'success': self.success,
            'url': self.url,
            'title': self.title,
            'content': self.content,
            'word_count': self.word_count,
            'images': self.images,
            'links': {
                'internal': self.internal_links,
                'external': self.external_links
            },
            'metadata': self.metadata,
            'error': self.error
        }