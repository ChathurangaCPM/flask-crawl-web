#!/usr/bin/env python3
import os
import sys
from app import create_app

def run():
    """Run the development server"""
    app = create_app('development')
    print("🚀 Starting Web Crawler API Server...")
    print("📍 Health check: http://localhost:5014/api/v1/health")
    print("🕷️  Crawl endpoint: POST http://localhost:5014/api/v1/crawl")
    print("📦 Batch crawl: POST http://localhost:5014/api/v1/crawl/batch")
    print("🔗 Quick crawl: GET http://localhost:5014/api/v1/crawl/<url>")
    app.run(debug=True, host='0.0.0.0', port=5014)

def test():
    """Run tests"""
    import pytest
    pytest.main(['-v', 'tests/'])

def shell():
    """Start interactive shell"""
    app = create_app('development')
    with app.app_context():
        import code
        code.interact(local=locals())

if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'run':
            run()
        elif command == 'test':
            test()
        elif command == 'shell':
            shell()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: run, test, shell")
    else:
        print("Usage: python manage.py [run|test|shell]")
        print("  run   - Start development server")
        print("  test  - Run test suite")
        print("  shell - Start interactive shell")