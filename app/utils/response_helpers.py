from flask import jsonify
from typing import Any, Dict

def success_response(data: Any, message: str = "Success") -> Any:
    """Create a standardized success response"""
    if isinstance(data, dict):
        return jsonify({
            "success": True,
            "message": message,
            **data
        })
    else:
        return jsonify({
            "success": True,
            "message": message,
            "data": data
        })

def error_response(message: str, status_code: int = 400, details: Dict = None) -> tuple:
    """Create a standardized error response"""
    response_data = {
        "success": False,
        "error": message
    }
    
    if details:
        response_data["details"] = details
    
    return jsonify(response_data), status_code

def paginated_response(data: list, page: int, per_page: int, total: int) -> Any:
    """Create a paginated response"""
    return jsonify({
        "success": True,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    })