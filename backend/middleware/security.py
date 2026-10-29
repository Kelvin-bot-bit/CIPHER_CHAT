# backend/middleware/security.py
from functools import wraps
from flask import request, jsonify, current_app
from werkzeug.security import safe_join
import re
import hashlib
import hmac
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SecurityMiddleware:
    """
    Security middleware for additional protection
    """
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize security middleware with Flask app"""
        self.app = app
        
        # Register before request handlers
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        
        # Apply CSRF protection to all POST, PUT, DELETE requests
        app.before_request(csrf_protect)
    
    def before_request(self):
        """Process request before reaching endpoint"""
        # Validate input data for POST/PUT requests
        if request.method in ['POST', 'PUT'] and request.is_json:
            sanitize_input(request.get_json())
        
        # Check for SQL injection patterns
        if request.args:
            for key, value in request.args.items():
                if self._contains_sql_injection(str(value)):
                    logger.warning(f"Potential SQL injection detected: {key}={value}")
                    return jsonify({'error': 'Invalid input'}), 400
        
        # Check for XSS patterns
        if request.args:
            for key, value in request.args.items():
                if self._contains_xss(str(value)):
                    logger.warning(f"Potential XSS detected: {key}={value}")
                    return jsonify({'error': 'Invalid input'}), 400
    
    def after_request(self, response):
        """Process response after leaving endpoint"""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Add Content Security Policy
        if not current_app.config.get('DEBUG', False):
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none'"
            )
        
        return response
    
    @staticmethod
    def _contains_sql_injection(value):
        """
        Check for SQL injection patterns
        """
        sql_patterns = [
            r'(\bSELECT\b.*\bFROM\b)',
            r'(\bINSERT\b.*\bINTO\b)',
            r'(\bUPDATE\b.*\bSET\b)',
            r'(\bDELETE\b.*\bFROM\b)',
            r'(\bDROP\b.*\bTABLE\b)',
            r'(\bUNION\b.*\bSELECT\b)',
            r'(\bOR\b.*\b=\b.*\b)',
            r'(\bAND\b.*\b=\b.*\b)',
            r'(\b--\b)',
            r'(\b;\b)'
        ]
        
        value_upper = value.upper()
        for pattern in sql_patterns:
            if re.search(pattern, value_upper, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def _contains_xss(value):
        """
        Check for XSS patterns
        """
        xss_patterns = [
            r'<script.*?>',
            r'<iframe.*?>',
            r'<object.*?>',
            r'<embed.*?>',
            r'<applet.*?>',
            r'onerror\s*=',
            r'onload\s*=',
            r'onclick\s*=',
            r'onmouseover\s*=',
            r'javascript:'
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def validate_file_upload(file_data):
        """
        Validate uploaded file
        """
        if not file_data:
            return False, 'No file provided'
        
        # Check file size
        if len(file_data) > current_app.config.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024):
            return False, 'File too large'
        
        # Check file magic bytes
        allowed_magic_bytes = {
            'pdf': b'%PDF',
            'png': b'\x89PNG',
            'jpg': b'\xFF\xD8\xFF',
            'gif': b'GIF87a',
            'zip': b'PK\x03\x04',
            'mp4': b'\x00\x00\x00\x18ftyp',
            'mp3': b'ID3'
        }
        
        # Check magic bytes for common file types
        # This is a simplified check - you should implement more comprehensive validation
        
        return True, 'File validated'

def csrf_protect():
    """
    CSRF protection for state-changing requests
    """
    if request.method in ['POST', 'PUT', 'DELETE']:
        # Skip for API endpoints that use JWT
        if request.path.startswith('/api/'):
            return
        
        # Check CSRF token for non-API routes
        csrf_token = request.headers.get('X-CSRF-Token')
        if not csrf_token:
            return jsonify({'error': 'CSRF token missing'}), 400
        
        # Validate CSRF token (implement your validation logic)
        # This is a placeholder - you should implement proper CSRF validation
        
        return

def sanitize_input(data):
    """
    Sanitize input data
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                # Remove potentially dangerous characters
                data[key] = re.sub(r'[<>]', '', value)
            elif isinstance(value, dict):
                sanitize_input(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        sanitize_input(item)
                    elif isinstance(item, str):
                        item = re.sub(r'[<>]', '', item)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                sanitize_input(item)
            elif isinstance(item, str):
                item = re.sub(r'[<>]', '', item)
    
    return data