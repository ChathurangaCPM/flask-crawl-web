# 🕷️ Web Crawler API - Complete Documentation

**Developer:** Infinitude Private Limited  
**API Version:** v1  
**Base URL:** `http://localhost:5014/api/v1` (Development) | `https://your-domain.com/api/v1` (Production)

## 📋 Table of Contents

1. [Authentication & Rate Limiting](#-authentication--rate-limiting)
2. [Health Check Endpoints](#-health-check-endpoints)
3. [Standard Web Crawling](#-standard-web-crawling)
4. [Content-Only Extraction](#-content-only-extraction)
5. [Selective Content Extraction](#-selective-content-extraction)
6. [Array-Based Content Extraction](#-array-based-content-extraction)
7. [Error Handling](#-error-handling)
8. [Code Examples](#-code-examples)

---

## 🔐 Authentication & Rate Limiting

### API Key Authentication (Optional)
Include API key in headers to bypass rate limits:
```
X-API-Key: your-api-key-here
```

### Rate Limits (Production Only)
| Endpoint | Rate Limit | Description |
|----------|------------|-------------|
| `POST /crawl` | 15/minute | Standard web crawling |
| `POST /crawl/fast` | 20/minute | Ultra-fast crawling |
| `POST /crawl/batch` | 3/minute | Batch URL crawling |
| `GET /crawl/<url>` | 30/minute | Quick GET crawling |
| `POST /content` | 20/minute | Content-only extraction |
| `POST /content/fast` | 30/minute | Ultra-fast content |
| `POST /content/selective` | 15/minute | Selective extraction |
| `POST /content/array` | 10/minute | Array extraction |
| **Global Limit** | 100/hour | Overall API usage |

**Note:** Rate limiting is disabled in development mode (`FLASK_ENV=development`)

---

## 🏥 Health Check Endpoints

### 1. Basic Health Check
**Endpoint:** `GET /api/v1/health`

**Response:**
```json
{
  "success": true,
  "status": "healthy",
  "service": "Web Crawler API",
  "version": "v1",
  "environment": "development",
  "timestamp": 1703123456.789
}
```

### 2. Detailed Health Check
**Endpoint:** `GET /api/v1/health/detailed`

**Response:**
```json
{
  "success": true,
  "status": "healthy",
  "service": "Web Crawler API",
  "version": "v1",
  "environment": "development",
  "system": {
    "cpu_percent": 25.5,
    "memory_percent": 60.2,
    "disk_usage": 45.8,
    "process_id": 12345
  },
  "timestamp": 1703123456.789
}
```

---

## 🕸️ Standard Web Crawling

### 1. Single URL Crawl
**Endpoint:** `POST /api/v1/crawl`  
**Rate Limit:** 15/minute

**Request Body:**
```json
{
  "url": "https://example.com",
  "config": {
    "max_content_length": 5000,
    "excluded_tags": ["nav", "footer", "script"],
    "exclude_external_links": true,
    "word_count_threshold": 10,
    "speed_mode": "fast",
    "skip_images": false,
    "skip_links": false,
    "use_cache": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "url": "https://example.com",
    "title": "Example Website",
    "content": "Page content here...",
    "word_count": 245,
    "images": [
      {
        "src": "https://example.com/image.jpg",
        "alt": "Image description",
        "title": "Image title"
      }
    ],
    "links": {
      "internal": [
        {
          "href": "/about",
          "text": "About Us"
        }
      ],
      "external": [
        {
          "href": "https://external.com",
          "text": "External Link"
        }
      ]
    },
    "metadata": {
      "crawl_time": 1.2,
      "status_code": 200,
      "api_response_time": 1.5,
      "user_agent_used": "Mozilla/5.0...",
      "mode": "fast"
    }
  }
}
```

### 2. Ultra-Fast Crawl
**Endpoint:** `POST /api/v1/crawl/fast`  
**Rate Limit:** 20/minute

**Request Body:**
```json
{
  "url": "https://example.com",
  "config": {
    "max_content_length": 2000
  }
}
```

**Response:** Same format as standard crawl but with `"mode": "ultra_fast"` in metadata.

### 3. Batch URL Crawling
**Endpoint:** `POST /api/v1/crawl/batch`  
**Rate Limit:** 3/minute

**Request Body:**
```json
{
  "urls": [
    "https://example1.com",
    "https://example2.com",
    "https://example3.com"
  ],
  "config": {
    "max_concurrent": 3,
    "max_content_length": 2000,
    "speed_mode": "fast",
    "skip_images": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "success": true,
        "url": "https://example1.com",
        "title": "Example 1",
        "content": "Content...",
        "word_count": 150
      },
      {
        "success": false,
        "url": "https://example2.com",
        "error": "Timeout error"
      }
    ],
    "total_processed": 3,
    "successful": 2,
    "failed": 1,
    "total_time": 4.2,
    "average_time_per_url": 1.4,
    "mode": "concurrent_batch"
  }
}
```

### 4. Quick GET Crawl
**Endpoint:** `GET /api/v1/crawl/<path:url>`  
**Rate Limit:** 30/minute

**Example:** `GET /api/v1/crawl/example.com`

**Response:** Same format as standard crawl with `"mode": "get_fast"`.

### 5. Crawl Service Test
**Endpoint:** `GET /api/v1/crawl/test`  
**Rate Limit:** 60/minute

**Response:**
```json
{
  "success": true,
  "message": "Crawler service is ready",
  "endpoints": {
    "single": "POST /api/v1/crawl",
    "fast": "POST /api/v1/crawl/fast",
    "batch": "POST /api/v1/crawl/batch",
    "get": "GET /api/v1/crawl/<url>"
  },
  "status": "healthy",
  "rate_limiting": {
    "environment": "development",
    "is_development": true,
    "rate_limit_active": false,
    "has_api_key": false,
    "api_key_valid": false
  }
}
```

---

## 📝 Content-Only Extraction

### 1. Extract Clean Text Content
**Endpoint:** `POST /api/v1/content`  
**Rate Limit:** 20/minute

**Features:**
- Removes all images and links
- Extracts only clean, readable text
- Prioritizes main content areas

**Request Body:**
```json
{
  "url": "https://example.com",
  "config": {
    "max_content_length": 5000
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "url": "https://example.com",
    "title": "Example Website",
    "content": "Clean text content without images or links...",
    "word_count": 245,
    "images": [],
    "links": {
      "internal": [],
      "external": []
    },
    "metadata": {
      "crawl_time": 0.8,
      "status_code": 200,
      "api_response_time": 1.2,
      "extraction_mode": "content_only",
      "images_removed": true,
      "links_removed": true,
      "endpoint": "content_only"
    }
  }
}
```

### 2. Ultra-Fast Content Extraction
**Endpoint:** `POST /api/v1/content/fast`  
**Rate Limit:** 30/minute

**Request Body:**
```json
{
  "url": "https://example.com",
  "config": {
    "max_content_length": 2000
  }
}
```

**Response:** Same format with `"endpoint": "content_only_ultra_fast"`.

### 3. Batch Content Extraction
**Endpoint:** `POST /api/v1/content/batch`  
**Rate Limit:** 5/minute

**Request Body:**
```json
{
  "urls": ["https://example1.com", "https://example2.com"],
  "config": {
    "max_content_length": 2000,
    "max_concurrent": 2
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "success": true,
        "url": "https://example1.com",
        "content": "Clean text content...",
        "word_count": 120
      }
    ],
    "total_processed": 2,
    "successful": 1,
    "failed": 1,
    "total_time": 3.5,
    "average_time_per_url": 1.75,
    "mode": "content_only_batch",
    "features": {
      "images_removed": true,
      "links_removed": true,
      "clean_text_only": true
    }
  }
}
```

### 4. Quick Content GET
**Endpoint:** `GET /api/v1/content/<path:url>`  
**Rate Limit:** 40/minute

**Example:** `GET /api/v1/content/example.com`

### 5. Content Service Test
**Endpoint:** `GET /api/v1/content/test`  
**Rate Limit:** 60/minute

---

## 🎯 Selective Content Extraction

### 1. Extract with Custom CSS Selectors
**Endpoint:** `POST /api/v1/content/selective`  
**Rate Limit:** 15/minute

**Features:**
- Use custom CSS selectors to target specific content
- Exclude unwanted sections
- Return individual sections

**Request Body:**
```json
{
  "url": "https://example.com",
  "config": {
    "selectors": [".main-content", "#article-body", ".post-content"],
    "exclude_selectors": [".advertisement", ".sidebar", ".comments"],
    "max_content_length": 5000,
    "return_sections": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "url": "https://example.com",
    "title": "Example Website",
    "content": "[.main-content]\nMain content here...\n\n[#article-body]\nArticle content...",
    "word_count": 456,
    "images": [],
    "links": {
      "internal": [],
      "external": []
    },
    "metadata": {
      "crawl_time": 1.5,
      "status_code": 200,
      "api_response_time": 2.1,
      "extraction_mode": "custom_selectors",
      "selectors_used": [".main-content", "#article-body"],
      "exclude_selectors_used": [".advertisement"],
      "total_sections": 2,
      "sections": {
        "selector_1_.main-content": {
          "selector": ".main-content",
          "content": "Main content here...",
          "element_count": 1,
          "word_count": 200
        },
        "selector_2_#article-body": {
          "selector": "#article-body",
          "content": "Article content...",
          "element_count": 1,
          "word_count": 256
        }
      },
      "endpoint": "selective_content"
    }
  }
}
```

### 2. Batch Selective Extraction
**Endpoint:** `POST /api/v1/content/selective/batch`  
**Rate Limit:** 3/minute

**Request Body:**
```json
{
  "urls": ["https://example1.com", "https://example2.com"],
  "config": {
    "selectors": [".content", "article"],
    "exclude_selectors": [".ads"],
    "max_content_length": 3000,
    "max_concurrent": 2
  }
}
```

### 3. Quick Selective GET
**Endpoint:** `GET /api/v1/content/selective/<path:url>`  
**Rate Limit:** 25/minute

**Query Parameters:**
- `selectors`: Comma-separated CSS selectors
- `exclude`: Comma-separated exclude selectors  
- `length`: Max content length

**Example:** `GET /api/v1/content/selective/example.com?selectors=.content,.main&exclude=.ads&length=2000`

### 4. Analyze Page Structure
**Endpoint:** `POST /api/v1/content/analyze`  
**Rate Limit:** 10/minute

**Request Body:**
```json
{
  "url": "https://example.com",
  "config": {
    "find_main_content": true,
    "suggest_selectors": true,
    "max_suggestions": 5
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis": {
      "url": "https://example.com",
      "title": "Example Website",
      "content_preview": "Page content preview...",
      "word_count": 456,
      "suggested_selectors": [
        {
          "selector": "main",
          "description": "Main content area"
        },
        {
          "selector": "article",
          "description": "Article content"
        },
        {
          "selector": ".content",
          "description": "Content class"
        }
      ],
      "exclude_suggestions": [
        {
          "selector": "nav",
          "description": "Navigation menus"
        },
        {
          "selector": ".sidebar",
          "description": "Sidebar content"
        }
      ],
      "analysis_time": 2.1
    },
    "next_steps": {
      "test_selectors": "Use POST /api/v1/content/selective with suggested selectors",
      "batch_extract": "Use POST /api/v1/content/selective/batch for multiple URLs",
      "get_quick": "Use GET /api/v1/content/selective/example.com?selectors=main,article"
    }
  }
}
```

### 5. Selective Service Test
**Endpoint:** `GET /api/v1/content/selective/test`  
**Rate Limit:** 60/minute

---

## 📊 Array-Based Content Extraction

### 1. Extract Repeated Elements as Arrays
**Endpoint:** `POST /api/v1/content/array`  
**Rate Limit:** 10/minute

**Perfect for:** News lists, product listings, search results, social media posts

**Request Body:**
```json
{
  "url": "https://news-site.com/latest",
  "config": {
    "array_selectors": {
      "news_stories": {
        "selector": ".news-story",
        "sub_selectors": {
          "title": "h2 a",
          "summary": "p",
          "date": ".date",
          "link": "h2 a",
          "image": ".thumb img"
        },
        "limit": 10
      },
      "trending_topics": {
        "selector": ".trending-item",
        "sub_selectors": {
          "topic": ".topic-title",
          "count": ".topic-count"
        },
        "limit": 5
      }
    },
    "exclude_selectors": [".advertisement", ".sidebar"],
    "format": "structured"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "url": "https://news-site.com/latest",
    "title": "Latest News",
    "content": "=== NEWS_STORIES (3 items) ===\n\n[Item 1]\nBreaking: Major Event Happens\ntitle: Breaking: Major Event Happens\nsummary: This is a summary of the breaking news...\ndate: 2024-01-15\n\n[Item 2]\nUpdate: Follow-up Story\ntitle: Update: Follow-up Story\nsummary: More details about the event...\ndate: 2024-01-15",
    "word_count": 156,
    "images": [],
    "links": {
      "internal": [],
      "external": []
    },
    "metadata": {
      "crawl_time": 2.3,
      "status_code": 200,
      "api_response_time": 3.1,
      "extraction_mode": "array_based",
      "array_selectors_used": ["news_stories", "trending_topics"],
      "format_output": "structured",
      "total_items_extracted": 8,
      "arrays": {
        "news_stories": {
          "selector": ".news-story",
          "items": [
            {
              "index": 0,
              "main_content": "Breaking: Major Event Happens This is a summary...",
              "title": "Breaking: Major Event Happens",
              "summary": "This is a summary of the breaking news...",
              "date": "2024-01-15",
              "link": "https://news-site.com/breaking-news",
              "word_count": 25,
              "char_count": 150
            },
            {
              "index": 1,
              "main_content": "Update: Follow-up Story More details...",
              "title": "Update: Follow-up Story",
              "summary": "More details about the event...",
              "date": "2024-01-15",
              "link": "https://news-site.com/follow-up",
              "word_count": 20,
              "char_count": 120
            }
          ],
          "count": 2,
          "sub_selectors_used": ["title", "summary", "date", "link"]
        },
        "trending_topics": {
          "selector": ".trending-item",
          "items": [
            {
              "index": 0,
              "main_content": "Politics 25 discussions",
              "topic": "Politics",
              "count": "25 discussions",
              "word_count": 3,
              "char_count": 22
            }
          ],
          "count": 1,
          "sub_selectors_used": ["topic", "count"]
        }
      },
      "endpoint": "array_content"
    },
    "arrays": {
      "news_stories": {
        "count": 2,
        "selector": ".news-story",
        "items": ["Breaking: Major Event Happens...", "Update: Follow-up Story..."]
      }
    },
    "arrays_preview": {
      "news_stories": {
        "count": 2,
        "selector": ".news-story",
        "items": ["Breaking: Major Event Happens This is a summary of the breaking news..."]
      }
    }
  }
}
```

### 2. Batch Array Extraction
**Endpoint:** `POST /api/v1/content/array/batch`  
**Rate Limit:** 2/minute

**Request Body:**
```json
{
  "urls": ["https://site1.com", "https://site2.com"],
  "config": {
    "array_selectors": {
      "articles": {
        "selector": ".article",
        "sub_selectors": {
          "title": "h2",
          "summary": ".excerpt"
        }
      }
    },
    "format": "structured",
    "max_concurrent": 2
  }
}
```

### 3. Quick Array GET
**Endpoint:** `GET /api/v1/content/array/<path:url>`  
**Rate Limit:** 20/minute

**Query Parameters:**
- `selector`: Main CSS selector for repeated elements
- `title`: Sub-selector for titles
- `summary`: Sub-selector for summaries
- `link`: Sub-selector for links
- `date`: Sub-selector for dates
- `exclude`: Comma-separated exclude selectors
- `limit`: Maximum items to extract
- `format`: Output format (structured, flat, summary)

**Example:** `GET /api/v1/content/array/news-site.com?selector=.news-item&title=h3&summary=p&limit=5&format=structured`

### 4. Demo with Pre-configured Examples
**Endpoint:** `POST /api/v1/content/array/demo`  
**Rate Limit:** 5/minute

**Request Body:**
```json
{
  "site_type": "adaderana_news",
  "url": "https://yournewssite.lk/hot-news/",
  "limit": 5
}
```

**Available site_types:**
- `adaderana_news`: News site configuration
- `generic_news`: Generic news articles
- `generic_products`: E-commerce products
- `generic_search`: Search results

### 5. Array Service Test
**Endpoint:** `GET /api/v1/content/array/test`  
**Rate Limit:** 60/minute

**Response includes:** Service status, usage examples, configuration guide, output formats

---

## ❌ Error Handling

### Standard Error Response Format
```json
{
  "success": false,
  "error": "Error message",
  "message": "Detailed error description",
  "details": {
    "additional": "context"
  }
}
```

### Common HTTP Status Codes
- `200` - Success
- `400` - Bad Request (Invalid input)
- `408` - Request Timeout
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
- `503` - Service Unavailable

### Rate Limit Exceeded Response
```json
{
  "success": false,
  "error": "Rate limit exceeded",
  "message": "Too many requests. Please try again later or use an API key for unlimited access.",
  "details": {
    "retry_after_seconds": 60,
    "api_key_header": "X-API-Key",
    "rate_limit_info": {
      "environment": "production",
      "documentation": "/api/v1/docs",
      "contact": "support@infinitude.lk"
    }
  }
}
```

---

## 💻 Code Examples

### JavaScript/Node.js

#### Basic Crawling
```javascript
const fetch = require('node-fetch');

async function crawlWebsite(url) {
  const response = await fetch('http://localhost:5014/api/v1/crawl', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-api-key-here' // Optional
    },
    body: JSON.stringify({
      url: url,
      config: {
        max_content_length: 3000,
        speed_mode: 'fast'
      }
    })
  });
  
  const data = await response.json();
  
  if (data.success) {
    console.log('Title:', data.data.title);
    console.log('Content:', data.data.content);
    console.log('Word Count:', data.data.word_count);
  } else {
    console.error('Error:', data.error);
  }
}

crawlWebsite('https://example.com');
```

#### Array-Based Extraction (News Site)
```javascript
async function extractNewsStories(url) {
  const response = await fetch('http://localhost:5014/api/v1/content/array', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      url: url,
      config: {
        array_selectors: {
          news_items: {
            selector: '.news-story',
            sub_selectors: {
              title: 'h2 a',
              summary: 'p',
              date: '.date',
              link: 'h2 a'
            },
            limit: 10
          }
        },
        format: 'structured'
      }
    })
  });
  
  const data = await response.json();
  
  if (data.success && data.data.arrays) {
    const newsItems = data.data.arrays.news_items.items;
    newsItems.forEach((item, index) => {
      console.log(`\n--- News Item ${index + 1} ---`);
      console.log('Title:', item.title);
      console.log('Summary:', item.summary);
      console.log('Date:', item.date);
      console.log('Link:', item.link);
    });
  }
}

extractNewsStories('https://news-site.com/latest');
```

#### Batch Processing
```javascript
async function batchCrawl(urls) {
  const response = await fetch('http://localhost:5014/api/v1/crawl/batch', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your-api-key-here'
    },
    body: JSON.stringify({
      urls: urls,
      config: {
        max_concurrent: 3,
        max_content_length: 2000,
        speed_mode: 'fast'
      }
    })
  });
  
  const data = await response.json();
  
  if (data.success) {
    console.log(`Processed ${data.data.total_processed} URLs`);
    console.log(`Successful: ${data.data.successful}, Failed: ${data.data.failed}`);
    
    data.data.results.forEach((result, index) => {
      if (result.success) {
        console.log(`${index + 1}. ${result.title} (${result.word_count} words)`);
      } else {
        console.log(`${index + 1}. Error: ${result.error}`);
      }
    });
  }
}

batchCrawl([
  'https://example1.com',
  'https://example2.com',
  'https://example3.com'
]);
```

#### Selective Content Extraction
```javascript
async function extractSpecificContent(url) {
  const response = await fetch('http://localhost:5014/api/v1/content/selective', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      url: url,
      config: {
        selectors: ['.main-content', 'article', '.post-body'],
        exclude_selectors: ['.advertisement', '.sidebar', '.comments'],
        max_content_length: 5000,
        return_sections: true
      }
    })
  });
  
  const data = await response.json();
  
  if (data.success) {
    console.log('Extracted content from sections:');
    Object.keys(data.data.metadata.sections).forEach(sectionKey => {
      const section = data.data.metadata.sections[sectionKey];
      console.log(`\n--- ${section.selector} ---`);
      console.log(section.content.substring(0, 200) + '...');
    });
  }
}

extractSpecificContent('https://blog.example.com/article');
```

### Python

#### Basic Usage
```python
import requests
import json

def crawl_website(url, api_key=None):
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['X-API-Key'] = api_key
    
    payload = {
        'url': url,
        'config': {
            'max_content_length': 3000,
            'speed_mode': 'fast',
            'exclude_external_links': True
        }
    }
    
    response = requests.post(
        'http://localhost:5014/api/v1/crawl',
        headers=headers,
        json=payload
    )
    
    data = response.json()
    
    if data['success']:
        print(f"Title: {data['data']['title']}")
        print(f"Word Count: {data['data']['word_count']}")
        print(f"Content: {data['data']['content'][:200]}...")
        print(f"Crawl Time: {data['data']['metadata']['crawl_time']}s")
    else:
        print(f"Error: {data['error']}")

# Usage
crawl_website('https://example.com', 'your-api-key-here')
```

#### Content-Only Extraction
```python
def extract_clean_content(url):
    payload = {
        'url': url,
        'config': {
            'max_content_length': 5000
        }
    }
    
    response = requests.post(
        'http://localhost:5014/api/v1/content',
        headers={'Content-Type': 'application/json'},
        json=payload
    )
    
    data = response.json()
    
    if data['success']:
        content = data['data']['content']
        print(f"Clean content (no images/links):")
        print(content)
        print(f"\nWord count: {data['data']['word_count']}")
    else:
        print(f"Error: {data['error']}")

extract_clean_content('https://blog.example.com/post')
```

### PHP

#### Basic Implementation
```php
<?php
function crawlWebsite($url, $apiKey = null) {
    $headers = ['Content-Type: application/json'];
    if ($apiKey) {
        $headers[] = 'X-API-Key: ' . $apiKey;
    }
    
    $data = [
        'url' => $url,
        'config' => [
            'max_content_length' => 3000,
            'speed_mode' => 'fast'
        ]
    ];
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, 'http://localhost:5014/api/v1/crawl');
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    $result = json_decode($response, true);
    
    if ($result['success']) {
        echo "Title: " . $result['data']['title'] . "\n";
        echo "Word Count: " . $result['data']['word_count'] . "\n";
        echo "Content: " . substr($result['data']['content'], 0, 200) . "...\n";
    } else {
        echo "Error: " . $result['error'] . "\n";
    }
}

crawlWebsite('https://example.com', 'your-api-key-here');
?>
```

### React.js/Next.js (for Infinitude's projects)

#### Custom Hook for Web Crawling
```javascript
// hooks/useWebCrawler.js
import { useState, useCallback } from 'react';

export const useWebCrawler = (apiKey = null) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const crawl = useCallback(async (url, config = {}) => {
    setLoading(true);
    setError(null);
    
    try {
      const headers = {
        'Content-Type': 'application/json',
      };
      
      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const response = await fetch('/api/crawl', {
        method: 'POST',
        headers,
        body: JSON.stringify({ url, config }),
      });

      const result = await response.json();

      if (result.success) {
        setData(result.data);
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey]);

  const extractArrayContent = useCallback(async (url, arraySelectors) => {
    setLoading(true);
    setError(null);
    
    try {
      const headers = {
        'Content-Type': 'application/json',
      };
      
      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const response = await fetch('/api/content/array', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          url,
          config: {
            array_selectors: arraySelectors,
            format: 'structured'
          }
        }),
      });

      const result = await response.json();

      if (result.success) {
        setData(result.data);
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey]);

  return {
    crawl,
    extractArrayContent,
    loading,
    error,
    data,
    clearError: () => setError(null),
    clearData: () => setData(null)
  };
};
```

#### React Component Example
```javascript
// components/WebCrawlerTool.jsx
import { useState } from 'react';
import { useWebCrawler } from '../hooks/useWebCrawler';

export default function WebCrawlerTool() {
  const [url, setUrl] = useState('');
  const [extractionType, setExtractionType] = useState('standard');
  const { crawl, extractArrayContent, loading, error, data } = useWebCrawler(
    process.env.NEXT_PUBLIC_CRAWLER_API_KEY
  );

  const handleCrawl = async () => {
    if (!url) return;

    if (extractionType === 'array') {
      // Example for news sites
      await extractArrayContent(url, {
        news_items: {
          selector: '.news-story, .article-item',
          sub_selectors: {
            title: 'h2, h3, .title',
            summary: 'p, .excerpt',
            date: '.date, .timestamp',
            link: 'a'
          },
          limit: 10
        }
      });
    } else {
      await crawl(url, {
        max_content_length: 5000,
        speed_mode: 'fast',
        exclude_external_links: true
      });
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Web Crawler Tool</h1>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Website URL
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com"
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Extraction Type
          </label>
          <select
            value={extractionType}
            onChange={(e) => setExtractionType(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
          >
            <option value="standard">Standard Crawl</option>
            <option value="content">Content Only</option>
            <option value="array">Array Extraction (News/Lists)</option>
          </select>
        </div>

        <button
          onClick={handleCrawl}
          disabled={loading || !url}
          className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Crawling...' : 'Start Crawling'}
        </button>
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded-md">
          Error: {error}
        </div>
      )}

      {data && (
        <div className="mt-6 space-y-4">
          <h2 className="text-2xl font-semibold">Results</h2>
          
          <div className="bg-gray-50 p-4 rounded-md">
            <h3 className="font-medium">Title: {data.title}</h3>
            <p className="text-sm text-gray-600">
              Word Count: {data.word_count} | 
              Crawl Time: {data.metadata?.crawl_time}s
            </p>
          </div>

          {extractionType === 'array' && data.arrays && (
            <div className="space-y-4">
              {Object.entries(data.arrays).map(([key, arrayData]) => (
                <div key={key} className="border rounded-md p-4">
                  <h3 className="font-semibold capitalize mb-2">
                    {key.replace('_', ' ')} ({arrayData.count} items)
                  </h3>
                  {arrayData.items.slice(0, 3).map((item, index) => (
                    <div key={index} className="mb-2 p-2 bg-gray-50 rounded">
                      <div className="font-medium">{item.title}</div>
                      <div className="text-sm text-gray-600">{item.summary}</div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {extractionType !== 'array' && (
            <div className="bg-white border rounded-md p-4">
              <h3 className="font-medium mb-2">Content</h3>
              <div className="text-sm text-gray-700 whitespace-pre-wrap">
                {data.content?.substring(0, 1000)}
                {data.content?.length > 1000 && '...'}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

---

## 🔧 Configuration Reference

### Standard Crawl Config Options
```json
{
  "word_count_threshold": 10,          // Minimum words per text block
  "excluded_tags": ["nav", "footer"],  // HTML tags to exclude
  "exclude_external_links": true,      // Skip external links
  "process_iframes": false,            // Process iframe content
  "remove_overlay_elements": true,     // Remove popups/overlays
  "use_cache": true,                   // Enable result caching
  "max_content_length": 5000,          // Maximum characters
  "speed_mode": "fast",                // "fast" or "normal"
  "skip_images": true,                 // Skip image processing
  "skip_links": false,                 // Skip link extraction
  "max_concurrent": 3                  // For batch requests
}
```

### Selective Content Config
```json
{
  "selectors": [".main-content", "article"],    // CSS selectors to extract
  "exclude_selectors": [".ads", ".sidebar"],    // CSS selectors to exclude
  "max_content_length": 5000,                   // Maximum characters
  "return_sections": true                       // Return individual sections
}
```

### Array Content Config
```json
{
  "array_selectors": {
    "news_items": {
      "selector": ".news-story",           // Main repeating element
      "sub_selectors": {                   // Extract specific parts
        "title": "h2 a",
        "summary": "p",
        "date": ".date",
        "link": "a"
      },
      "limit": 10                          // Maximum items to extract
    }
  },
  "exclude_selectors": [".ads"],          // Elements to remove
  "format": "structured"                  // "structured", "flat", "summary"
}
```

---

## 🌟 Best Practices

### 1. URL Validation
- Always include protocol (`https://` or `http://`)
- Validate URLs before sending requests
- Handle redirects gracefully

### 2. Rate Limiting
- Use API keys in production for unlimited access
- Monitor rate limit headers in responses
- Implement retry logic with exponential backoff
- Cache results when possible

### 3. Error Handling
```javascript
// Robust error handling example
async function robustCrawl(url) {
  try {
    const response = await fetch('/api/v1/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });

    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After') || 60;
      console.log(`Rate limited. Retry after ${retryAfter}s`);
      return null;
    }

    const data = await response.json();
    return data.success ? data.data : null;
    
  } catch (error) {
    console.error('Crawl failed:', error.message);
    return null;
  }
}
```

### 4. Performance Optimization
- Use `/fast` endpoints for quick results
- Batch multiple URLs when possible
- Set appropriate `max_content_length` limits
- Use selective extraction for specific content

### 5. Content Extraction Strategy
- **Standard crawl**: Full page with images and links
- **Content-only**: Clean text without media
- **Selective**: Target specific sections with CSS selectors
- **Array-based**: Extract repeated elements (news, products, etc.)

---

## 📞 Support & Contact

**Developed by:** Infinitude Private Limited  
**Services:** Web Development, Software Development, IoT Development  
**Email:** support@infinitude.lk  
**Documentation:** This README file  

### Quick Start Checklist
- [ ] Install and run the API server
- [ ] Test with `/api/v1/health` endpoint
- [ ] Try basic crawling with `/api/v1/crawl`
- [ ] Set up API key for production use
- [ ] Choose appropriate extraction method for your use case
- [ ] Implement error handling and retry logic

---

*Last Updated: January 2025*  
*API Version: v1*