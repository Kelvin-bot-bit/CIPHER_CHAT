# backend/middleware/rate_limiter.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import jsonify, request
from functools import wraps
import time
import logging

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

class RateLimiter:
    """
    Custom rate limiter with additional features
    """
    def __init__(self, app=None):
        self.app = app
        self.rate_limits = {}
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize rate limiter with Flask app"""
        self.app = app
        limiter.init_app(app)
        
        # Register error handler
        @app.errorhandler(429)
        def ratelimit_handler(e):
            return jsonify({
                'error': 'Rate limit exceeded',
                'message': 'Too many requests. Please try again later.'
            }), 429
    
    @staticmethod
    def limit(limit_value):
        """
        Apply rate limit to a route
        """
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                # Get client IP
                client_ip = get_remote_address()
                
                # Check rate limit
                key = f"{client_ip}:{f.__name__}"
                
                # Parse limit (e.g., "10 per minute")
                parts = limit_value.split()
                if len(parts) != 3:
                    return f(*args, **kwargs)
                
                count = int(parts[0])
                period = parts[2]
                
                # Calculate period in seconds
                period_seconds = {
                    'second': 1,
                    'minute': 60,
                    'hour': 3600,
                    'day': 86400
                }.get(period.lower(), 60)
                
                # Store rate limit data in request context
                if not hasattr(request, 'rate_limit_data'):
                    request.rate_limit_data = {}
                
                request.rate_limit_data[key] = {
                    'limit': count,
                    'period': period_seconds,
                    'remaining': count,
                    'reset': time.time() + period_seconds
                }
                
                return f(*args, **kwargs)
            
            return limiter.limit(limit_value)(decorated_function)
        
        return decorator
    
    @staticmethod
    def get_rate_limit_headers():
        """
        Get rate limit headers for response
        """
        headers = {}
        
        if hasattr(request, 'rate_limit_data'):
            for key, data in request.rate_limit_data.items():
                headers['X-RateLimit-Limit'] = str(data['limit'])
                headers['X-RateLimit-Remaining'] = str(data['remaining'])
                headers['X-RateLimit-Reset'] = str(int(data['reset']))
        
        return headers

# Predefined rate limits
RATE_LIMITS = {
    'auth': {
        'login': '10 per minute',
        'register': '5 per hour',
        'forgot_password': '3 per hour',
        'reset_password': '3 per hour'
    },
    'messages': {
        'send': '60 per minute',
        'edit': '30 per minute',
        'delete': '30 per minute'
    },
    'friends': {
        'send_request': '30 per hour',
        'accept_request': '30 per hour'
    },
    'files': {
        'upload': '20 per hour',
        'download': '100 per hour'
    }
}

# Apply rate limits to specific endpoints
def apply_rate_limits(app):
    """
    Apply rate limits to all routes
    """
    for route in app.url_map.iter_rules():
        if route.rule.startswith('/api/'):
            # Get the endpoint name
            endpoint = route.endpoint
            
            # Apply rate limit based on endpoint
            if 'login' in endpoint:
                limiter.limit(RATE_LIMITS['auth']['login'])(app.view_functions[endpoint])
            elif 'register' in endpoint:
                limiter.limit(RATE_LIMITS['auth']['register'])(app.view_functions[endpoint])
            elif 'send_message' in endpoint or 'send' in endpoint:
                limiter.limit(RATE_LIMITS['messages']['send'])(app.view_functions[endpoint])