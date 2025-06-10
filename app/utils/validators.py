import re
from urllib.parse import urlparse
from typing import Dict, Any, List

def validate_url(url: str) -> bool:
    """Validate if URL is properly formatted"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def validate_crawl_request(data: Dict[str, Any]) -> tuple[bool, str]:
    """Validate crawl request data"""
    if not data:
        return False, "Request body is required"
    
    if 'url' not in data:
        return False, "URL is required"
    
    url = data['url']
    if not isinstance(url, str) or not validate_url(url):
        return False, "Invalid URL format"
    
    return True, ""

def validate_batch_request(data: Dict[str, Any], max_batch_size: int = 10) -> tuple[bool, str]:
    """Validate batch crawl request"""
    if not data:
        return False, "Request body is required"
    
    if 'urls' not in data:
        return False, "URLs array is required"
    
    urls = data['urls']
    if not isinstance(urls, list):
        return False, "URLs must be an array"
    
    if len(urls) == 0:
        return False, "At least one URL is required"
    
    if len(urls) > max_batch_size:
        return False, f"Maximum {max_batch_size} URLs allowed per batch"
    
    for url in urls:
        if not isinstance(url, str) or not validate_url(url):
            return False, f"Invalid URL format: {url}"
    
    return True, ""