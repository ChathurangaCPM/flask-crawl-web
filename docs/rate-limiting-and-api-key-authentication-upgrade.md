# Rate Limiting & API Key Authentication Upgrade

### 📋 Overview

This upgrade introduces intelligent rate limiting with API key authentication for the Web Crawler API. The system automatically adapts based on your environment and authentication status, providing unlimited access during development while protecting the production API from abuse.

### 🚀 What's New

#### 1. **Environment-Aware Rate Limiting**

* **Development Mode**: No rate limits - build and test freely
* **Production Mode**: Smart rate limits with API key bypass option

#### 2. **API Key Authentication**

* Secure API key validation
* Unlimited access for authenticated requests
* Per-endpoint customized rate limits

#### 3. **Enhanced Error Handling**

* Clear rate limit exceeded messages
* Retry-After headers for smart client retry logic
* Detailed rate limit status in responses

### 📦 Installation & Setup

#### 1. **Update Dependencies**

```bash
bashpip install -r requirements.txt
```

#### 2. **Environment Configuration**

**Development Setup**

```bash
# .env
FLASK_ENV=development
API_KEY=dev-test-key  # Optional in development
```

**Production Setup**

```bash
# .env
FLASK_ENV=production
API_KEY=your-secure-api-key-here  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 3. **Generate Secure API Key**

```bash
bashpython -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 🔧 Configuration

#### Rate Limits by Endpoint

| Endpoint                   | Rate Limit | Description                |
| -------------------------- | ---------- | -------------------------- |
| `POST /api/v1/crawl`       | 15/minute  | Standard web crawling      |
| `POST /api/v1/crawl/fast`  | 20/minute  | Ultra-fast text extraction |
| `POST /api/v1/crawl/batch` | 3/minute   | Batch URL processing       |
| `GET /api/v1/crawl/<url>`  | 30/minute  | Quick GET crawling         |
| **Global Limit**           | 100/hour   | Overall API usage cap      |

#### Environment Variables

```bash
# Required
FLASK_ENV=development|production  # Controls rate limiting behavior
API_KEY=your-secure-key          # API key for unlimited access

# Optional
RATELIMIT_STORAGE_URL=redis://localhost:6379/0  # Use Redis for distributed rate limiting
RATELIMIT_DEFAULT=100 per hour                   # Default global rate limit
```

### 💻 Usage Examples

#### 1. **Check Rate Limit Status**

```bash
# Check your current rate limit status
curl http://localhost:5014/api/v1/crawl/test

# With API key
curl http://localhost:5014/api/v1/crawl/test \
  -H "X-API-Key: your-api-key-here"
```

**Response:**

```json
{
  "success": true,
  "message": "Crawler service is ready",
  "status": "healthy",
  "rate_limiting": {
    "environment": "production",
    "is_development": false,
    "rate_limit_active": true,
    "has_api_key": false,
    "api_key_valid": false
  }
}
```

#### 2. **Making Authenticated Requests**

**Using cURL**

```bash
curl -X POST http://localhost:5014/api/v1/crawl \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "url": "https://example.com",
    "config": {
      "max_content_length": 2000
    }
  }'
```

**Using Python**

```python
import requests

headers = {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key-here'
}

response = requests.post(
    'http://localhost:5014/api/v1/crawl',
    json={'url': 'https://example.com'},
    headers=headers
)

print(response.json())
```

**Using Node.js/JavaScript**

```javascript
const response = await fetch('http://localhost:5014/api/v1/crawl', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-API-Key': 'your-api-key-here'
    },
    body: JSON.stringify({ 
        url: 'https://example.com',
        config: { max_content_length: 2000 }
    })
});

const data = await response.json();
console.log(data);
```

#### 3. **Handling Rate Limit Errors**

When rate limited, you'll receive a 429 response:

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

**Response Headers:**

```
X-RateLimit-Limit: 15
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1623456789
Retry-After: 60
```

### 🔄 Migration Guide

#### For Existing Users

1. **Development Environment**: No changes needed - rate limiting is automatically disabled
2. **Production Environment**:
   * Generate and set an API key in your environment
   * Update your API clients to include the `X-API-Key` header
   * Monitor rate limit headers in responses

#### Example Migration

**Before (no authentication):**

```python
response = requests.post(
    'http://api.infinitude.lk/api/v1/crawl',
    json={'url': 'https://example.com'}
)
```

**After (with API key):**

```python
response = requests.post(
    'http://api.infinitude.lk/api/v1/crawl',
    json={'url': 'https://example.com'},
    headers={'X-API-Key': 'your-api-key-here'}
)
```

### 🛡️ Security Best Practices

1. **API Key Management**
   * Never commit API keys to version control
   * Use environment variables or secure key vaults
   * Rotate keys regularly (recommended: every 90 days)
2. **HTTPS Only**
   * Always use HTTPS in production
   * Never send API keys over unencrypted connections
3.  **Key Storage**

    ```bash
    # Good: Environment variable
    export API_KEY="your-secure-key"

    # Bad: Hardcoded in source
    API_KEY = "your-secure-key"  # Never do this!
    ```
4. **Client-Side Security**
   * Never expose API keys in client-side code
   * Use server-side proxy for browser applications

### 📊 Monitoring & Debugging

#### Check Rate Limit Headers

```python
response = requests.post('http://localhost:5014/api/v1/crawl', json={...})

print(f"Limit: {response.headers.get('X-RateLimit-Limit')}")
print(f"Remaining: {response.headers.get('X-RateLimit-Remaining')}")
print(f"Reset: {response.headers.get('X-RateLimit-Reset')}")
```

#### Debug Rate Limiting Issues

```bash
# 1. Verify environment
echo $FLASK_ENV

# 2. Check API key is set
echo $API_KEY | head -c 10  # Show first 10 chars only

# 3. Test with curl including verbose headers
curl -v -X POST http://localhost:5014/api/v1/crawl/test \
  -H "X-API-Key: your-api-key"
```

### 🔧 Advanced Configuration

#### Custom Rate Limits

```python
# In app/api/v1/crawl.py
@apply_rate_limit("30 per minute")  # Custom limit
def custom_endpoint():
    pass
```

#### Redis Backend (Recommended for Production)

```bash
# Install Redis
sudo apt-get install redis-server

# Configure in .env
RATELIMIT_STORAGE_URL=redis://localhost:6379/0
```

#### Multiple API Keys

```python
# Support multiple keys (customize in app/api/v1/crawl.py)
VALID_API_KEYS = [
    os.getenv('API_KEY_1'),
    os.getenv('API_KEY_2'),
    os.getenv('API_KEY_3')
]
```

### 🐛 Troubleshooting

#### Issue: Rate limits applied in development

**Solution:**

```bash
# Verify environment
echo $FLASK_ENV  # Should output: development

# Set correctly
export FLASK_ENV=development
```

#### Issue: API key not working

**Solution:**

```bash
# Check exact header format
curl -v -H "X-API-Key: your-key" ...  # Correct
curl -v -H "x-api-key: your-key" ...  # Wrong (case sensitive)
curl -v -H "API-Key: your-key" ...    # Wrong (missing X-)
```

#### Issue: Different limits than expected

**Check:**

* Redis connection (if using)
* Environment variables loaded correctly
* No typos in rate limit decorators

### 📝 Client Implementation Examples

#### Python Client with Retry Logic

```python
class CrawlerClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "http://localhost:5014"
    
    def crawl(self, url, max_retries=3):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        
        for attempt in range(max_retries):
            response = requests.post(
                f"{self.base_url}/api/v1/crawl",
                json={'url': url},
                headers=headers
            )
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                print(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            
            return response.json()
        
        raise Exception("Max retries exceeded")

# Usage
client = CrawlerClient(api_key="your-key")
result = client.crawl("https://example.com")
```

#### Node.js Client with Exponential Backoff

```javascript
class CrawlerClient {
    constructor(apiKey = null) {
        this.apiKey = apiKey;
        this.baseUrl = 'http://localhost:5014';
    }
    
    async crawl(url, maxRetries = 3) {
        const headers = { 'Content-Type': 'application/json' };
        if (this.apiKey) {
            headers['X-API-Key'] = this.apiKey;
        }
        
        for (let i = 0; i < maxRetries; i++) {
            const response = await fetch(`${this.baseUrl}/api/v1/crawl`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ url })
            });
            
            if (response.status === 429) {
                const retryAfter = response.headers.get('Retry-After') || 60;
                console.log(`Rate limited. Retry after ${retryAfter}s`);
                await new Promise(r => setTimeout(r, retryAfter * 1000));
                continue;
            }
            
            return await response.json();
        }
        throw new Error('Max retries exceeded');
    }
}
```
