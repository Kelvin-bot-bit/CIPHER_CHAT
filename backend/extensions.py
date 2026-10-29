# backend/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_mail import Mail
from flask_cors import CORS

# Database
db = SQLAlchemy()

# JWT Authentication
jwt = JWTManager()

# Bcrypt for password hashing
bcrypt = Bcrypt()

# Database migrations
migrate = Migrate()

# WebSocket
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)

# Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],
    storage_uri="memory://"
)

# Cache
cache = Cache(
    config={
        'CACHE_TYPE': 'simple',
        'CACHE_DEFAULT_TIMEOUT': 300
    }
)

# Email
mail = Mail()

# CORS (will be configured in app.py)
cors = CORS()

# JWT callbacks
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    """Handle expired token"""
    from flask import jsonify
    return jsonify({
        'error': 'Token Expired',
        'message': 'Your access token has expired. Please refresh.'
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    """Handle invalid token"""
    from flask import jsonify
    return jsonify({
        'error': 'Invalid Token',
        'message': str(error)
    }), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    """Handle missing token"""
    from flask import jsonify
    return jsonify({
        'error': 'Authorization Required',
        'message': 'No token provided. Please login.'
    }), 401

@jwt.needs_fresh_token_loader
def token_not_fresh_callback(jwt_header, jwt_payload):
    """Handle non-fresh token"""
    from flask import jsonify
    return jsonify({
        'error': 'Fresh Token Required',
        'message': 'Please provide a fresh token.'
    }), 401

@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    """Handle revoked token"""
    from flask import jsonify
    return jsonify({
        'error': 'Token Revoked',
        'message': 'Your token has been revoked.'
    }), 401

# Database event listeners
@db.event.listens_for(db.Model, 'before_insert')
def model_before_insert(mapper, connection, target):
    """Add created_at timestamp if available"""
    if hasattr(target, 'created_at') and target.created_at is None:
        from datetime import datetime
        target.created_at = datetime.utcnow()

@db.event.listens_for(db.Model, 'before_update')
def model_before_update(mapper, connection, target):
    """Add updated_at timestamp if available"""
    if hasattr(target, 'updated_at'):
        from datetime import datetime
        target.updated_at = datetime.utcnow()

# Global application context
class AppContext:
    """Application context for non-request operations"""
    def __init__(self, app=None):
        self.app = app
    
    def __enter__(self):
        if self.app:
            self.context = self.app.app_context()
            self.context.push()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'context'):
            self.context.pop()

# Utility function to get current app context
def get_app_context():
    """Get the current application context"""
    from flask import current_app
    return current_app.app_context()

# Utility function to get database session
def get_db():
    """Get the current database session"""
    return db.session

# Utility function to commit database changes
def commit_db():
    """Commit the current database session"""
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        raise e

# Utility function to rollback database changes
def rollback_db():
    """Rollback the current database session"""
    db.session.rollback()

# Export all extensions
__all__ = [
    'db',
    'jwt',
    'bcrypt',
    'migrate',
    'socketio',
    'limiter',
    'cache',
    'mail',
    'cors',
    'get_db',
    'commit_db',
    'rollback_db',
    'get_app_context',
    'AppContext'
]