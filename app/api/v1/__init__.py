from flask import Blueprint

api_v1 = Blueprint('api_v1', __name__)

from . import crawl, health, content_only, enhanced_content, array_content