# backend/middleware/auth_middleware.py
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from models import User, Message, Group, GroupMember
from extensions import db
import logging

logger = logging.getLogger(__name__)

def admin_required(f):
    """
    Decorator to check if user is admin
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            user = User.query.get(user_id)
            
            if not user or not user.is_admin:
                return jsonify({'error': 'Admin privileges required'}), 403
            
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Admin required error: {str(e)}")
            return jsonify({'error': 'Authentication required'}), 401
    
    return decorated_function

def check_message_access(f):
    """
    Decorator to check if user has access to a message
    """
    @wraps(f)
    def decorated_function(message_id, *args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            
            message = Message.query.get(message_id)
            if not message:
                return jsonify({'error': 'Message not found'}), 404
            
            # Check access based on message type
            has_access = False
            
            if message.recipient_type == 'user':
                # User can access if sender or recipient
                has_access = (message.sender_id == user_id or 
                            message.recipient_id == user_id)
            elif message.recipient_type == 'group':
                # User can access if member of group
                group = Group.query.get(message.recipient_id)
                if group:
                    has_access = group.is_member(user_id)
            
            if not has_access:
                return jsonify({'error': 'Access denied'}), 403
            
            return f(message_id, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Message access check error: {str(e)}")
            return jsonify({'error': 'Authentication required'}), 401
    
    return decorated_function

def check_chat_access(f):
    """
    Decorator to check if user has access to a chat
    """
    @wraps(f)
    def decorated_function(chat_id, chat_type, *args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            
            has_access = False
            
            if chat_type == 'user':
                # Check if users are friends
                from services.friend_service import FriendService
                has_access = FriendService.are_friends(user_id, chat_id)
            elif chat_type == 'group':
                # Check if user is a member
                group = Group.query.get(chat_id)
                if group:
                    has_access = group.is_member(user_id)
            
            if not has_access:
                return jsonify({'error': 'Access denied'}), 403
            
            return f(chat_id, chat_type, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Chat access check error: {str(e)}")
            return jsonify({'error': 'Authentication required'}), 401
    
    return decorated_function

class AuthMiddleware:
    """
    Authentication middleware
    """
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize middleware with Flask app"""
        self.app = app
        app.before_request(self.before_request)
        app.after_request(self.after_request)
    
    def before_request(self):
        """Process request before it reaches the endpoint"""
        # Skip authentication for health check and static files
        if request.path in ['/health', '/', '/favicon.ico']:
            return
        
        # Skip for public routes
        public_routes = ['/api/auth/login', '/api/auth/register', '/api/auth/forgot-password']
        if any(request.path.startswith(route) for route in public_routes):
            return
        
        # Verify JWT for protected routes
        try:
            verify_jwt_in_request()
        except Exception as e:
            if not request.path.startswith('/api/'):
                return
            return jsonify({'error': 'Authentication required'}), 401
    
    def after_request(self, response):
        """Process response after it leaves the endpoint"""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response