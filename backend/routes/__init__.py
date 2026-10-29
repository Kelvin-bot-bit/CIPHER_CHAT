# backend/routes/__init__.py
"""
Routes package for Secure Chat Application
All API endpoints and route handlers
"""

from .auth import auth_bp
from .messages import messages_bp
from .friends import friends_bp
from .groups import groups_bp
from .files import files_bp
from .users import users_bp
from .admin import admin_bp

__all__ = [
    'auth_bp',
    'messages_bp',
    'friends_bp',
    'groups_bp',
    'files_bp',
    'users_bp',
    'admin_bp'
]