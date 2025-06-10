
A production-ready Flask API for web crawling with rate limiting, caching, and comprehensive error handling.

## Features

- ✅ Async web crawling with crawl4ai
- ✅ Rate limiting and request throttling
- ✅ Batch processing support
- ✅ Comprehensive error handling
- ✅ Health check endpoints
- ✅ Docker containerization
- ✅ Prometheus metrics
- ✅ Structured logging
- ✅ CORS support
- ✅ Input validation
- ✅ Unit tests

## Quick Start

1. **Clone and setup**:
   ```bash
   git clone <repository>
   cd web-crawler-api
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run development server**:
   ```bash
   python manage.py run
   ```

4. **Run with Docker**:
   ```bash
   docker-compose up --build
   ```

## API Endpoints

### Health Check
```bash
GET /api/v1/health
```

### Single URL Crawl
```bash
POST /api/v1/crawl
Content-Type: application/json

{
  "url": "https://example.com",
  "config": {
    "word_count_threshold": 10,
    "excluded_tags": ["nav", "footer"]
  }
}
```

### Batch Crawl
```bash
POST /api/v1/crawl/batch
Content-Type: application/json

{
  "urls": ["https://example1.com", "https://example2.com"],
  "config": {
    "word_count_threshold": 5
  }
}
```

## Production Deployment

See `docs/deployment_guide.md` for detailed deployment instructions.

## Testing

```bash
pytest tests/
```

## Configuration

All configuration is environment-based. See `.env.example` for available options.

## License

MIT License