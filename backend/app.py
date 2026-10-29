# backend/app.py - Fixed Version
#
# eventlet.monkey_patch() MUST run before anything else in the process —
# before importing os, logging, Flask, or any of the stdlib modules that
# touch sockets/threading/time. Those imports bind references to the
# *original* stdlib implementations; patching afterward leaves every
# module that already imported (including this file's own `import os`
# two lines down, previously) using unpatched, blocking I/O. Under
# eventlet's cooperative-concurrency model that means the server can't
# properly multiplex multiple simultaneous long-lived WebSocket
# connections — exactly the failure mode of "two people both need a
# stable socket open at once for a call, and it doesn't reliably work,
# even though single quick requests are fine." This was previously
# imported only inside the `if __name__ == '__main__':` block at the
# bottom of this file, by which point dozens of other modules (including
# Flask itself) had already been imported unpatched — so it was never
# actually taking effect.
import eventlet
eventlet.monkey_patch()

import os
import logging
from datetime import datetime
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_mail import Mail
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import extensions
from extensions import (
    db, jwt, bcrypt, migrate, socketio, 
    limiter, cache, mail
)

# Import models
from models import User, Message, Friend, Group, Notification
from utils.logger import setup_logging
from utils.redact import redact
from middleware.observability import init_observability, record_exception
from utils.schema_upgrade import ensure_observability_schema

def create_app(config_class=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration.
    # config.py already defines DevelopmentConfig/TestingConfig/ProductionConfig
    # plus a get_config() helper that maps FLASK_ENV to the right one — but
    # this factory was never calling it, so every run (including local dev
    # with FLASK_ENV=development in .env) loaded the bare `Config` base
    # class instead. That class never sets RATELIMIT_ENABLED, and
    # Flask-Limiter defaults that to True when unset, so rate limiting
    # silently stayed on in "development" regardless of the .env setting.
    if config_class:
        app.config.from_object(config_class)
    else:
        from config import get_config
        app.config.from_object(get_config())
    
    # Structured logging (JSON files + live ring buffer) must be up before
    # anything else logs, so start-up problems are captured too.
    setup_logging(app)
    
    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")
    limiter.init_app(app)
    cache.init_app(app)
    mail.init_app(app)
    
    # call_logs / group_call_logs were added after the original schema was
    # created. Create just those tables if they're missing, so an existing database picks it up on
    # the next start with no manual migration step. checkfirst makes this a
    # no-op once it exists (and safe under the dev reloader's double start).
    with app.app_context():
        try:
            from models.call_log import CallLog, GroupCallLog
            for table in (CallLog.__table__, GroupCallLog.__table__):
                table.create(bind=db.engine, checkfirst=True)
        except Exception as e:
            app.logger.error(f"Could not ensure the call log tables exist: {e}")
    
    # Bring the audit/monitoring tables and columns up to date (idempotent).
    ensure_observability_schema(app)
    
    # Request ids, timing, access log, DB query timing, activity audit trail.
    # Registered before the handlers below so it wraps everything.
    init_observability(app)
    
    # Configure CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": app.config['CORS_ORIGINS'],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "expose_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "max_age": 3600
        }
    })
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.messages import messages_bp
    from routes.friends import friends_bp
    from routes.groups import groups_bp
    from routes.files import files_bp
    from routes.users import users_bp
    from routes.admin import admin_bp
    from routes.notifications import notifications_bp
    from routes.voice import voice_bp
    from routes.push import push_bp
    from routes.status import status_bp
    from routes.calls import calls_bp
    from routes.monitoring import monitoring_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(friends_bp, url_prefix='/api/friends')
    app.register_blueprint(groups_bp, url_prefix='/api/groups')
    app.register_blueprint(files_bp, url_prefix='/api/files')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(monitoring_bp, url_prefix='/api/admin/monitoring')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(voice_bp, url_prefix='/api/voice')
    app.register_blueprint(push_bp, url_prefix='/api/push')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(calls_bp, url_prefix='/api/calls')
    
    # Register socket events
    from socket_events.chat_events import register_chat_events
    from socket_events.typing_events import register_typing_events
    from socket_events.presence_events import register_presence_events
    from socket_events.call_events import register_call_events
    from socket_events.group_call_events import register_group_call_events
    
    register_chat_events(socketio)
    register_typing_events(socketio)
    register_presence_events(socketio)
    register_call_events(socketio)
    register_group_call_events(socketio)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register before request handlers
    @app.before_request
    def before_request():
        """Log request information"""
        g.start_time = datetime.utcnow()
        
        # Log request details in debug mode
        if app.debug:
            app.logger.debug(f"Request: {request.method} {request.path}")
            # Only try to get JSON if content-type is application/json.
            # Bodies are redacted: passwords/tokens must never reach the logs.
            if request.is_json:
                try:
                    app.logger.debug(f"Request Body: {redact(request.get_json(silent=True))}")
                except Exception as e:
                    app.logger.debug(f"Could not parse JSON: {e}")
    
    @app.after_request
    def after_request(response):
        """Add response headers and log request completion"""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Add CORS headers for WebSocket
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        
        # Log request completion
        if hasattr(g, 'start_time'):
            elapsed = (datetime.utcnow() - g.start_time).total_seconds()
            app.logger.debug(f"Request completed in {elapsed:.4f}s")
        
        return response
    
    # Health check endpoint
    @app.route('/health')
    def health_check():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
        }), 200
    
    @app.route('/health/ready')
    def readiness_check():
        """Readiness probe: 200 only if the database answers (for load balancers / uptime monitors)."""
        from services import monitoring_service
        result = monitoring_service.check_database()
        ok = result['status'] in ('ok', 'warn')
        return jsonify({
            'status': 'ready' if ok else 'unavailable',
            'database': result['status'],
            'database_latency_ms': result.get('latency_ms'),
            'timestamp': datetime.utcnow().isoformat()
        }), 200 if ok else 503
    
    @app.route('/')
    def index():
        """Root endpoint"""
        return jsonify({
            'message': 'Secure Chat Application API',
            'version': '1.0.0',
            'status': 'running',
            'documentation': '/api/docs'
        }), 200
    
    # Disappearing-messages cleanup — soft-deletes messages whose
    # expires_at has passed, on a periodic sweep (see
    # services/cleanup_service.py for why this isn't more real-time than
    # that). Started here rather than at import time so it only runs
    # once the app is fully configured, and only once per process even
    # under the debug reloader.
    from services.cleanup_service import start_cleanup_scheduler
    start_cleanup_scheduler(app)
    
    # Background health checks + alert evaluation.
    from services.monitoring_service import start_monitoring
    start_monitoring(app)
    
    return app

def register_error_handlers(app):
    """Register global error handlers"""
    
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({
            'error': 'Bad Request',
            'message': str(e.description) if hasattr(e, 'description') else 'Invalid request'
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required'
        }), 401
    
    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({
            'error': 'Forbidden',
            'message': 'You do not have permission to access this resource'
        }), 403
    
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            'error': 'Not Found',
            'message': 'Resource not found'
        }), 404
    
    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            'error': 'Method Not Allowed',
            'message': 'HTTP method not allowed for this endpoint'
        }), 405
    
    @app.errorhandler(415)
    def unsupported_media_type(e):
        return jsonify({
            'error': 'Unsupported Media Type',
            'message': 'Content-Type must be application/json for JSON requests'
        }), 415
    
    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({
            'error': 'Rate Limit Exceeded',
            'message': 'Too many requests. Please try again later.'
        }), 429
    
    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Internal Server Error: {str(e)}")
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'Something went wrong on the server'
        }), 500
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Deliberate HTTP errors (413 too large, 409 conflict, ...) keep their
        # own status instead of being reported as a server crash.
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({'error': e.name, 'message': e.description}), e.code
        # Logs the stack trace, stores a system event and raises an alert.
        record_exception(e)
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred'
        }), 500

# Application entry point
if __name__ == '__main__':
    app = create_app()
    
    # Get configuration from environment
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🔐 Secure Chat Application")
    print("=" * 60)
    print(f"📡 Server: http://{host}:{port}")
    print(f"🐛 Debug Mode: {debug_mode}")
    print(f"📊 Environment: {os.environ.get('FLASK_ENV', 'development')}")
    print("=" * 60)
    
    # Check if running with eventlet
    try:
        import eventlet
        
        # Try to run with eventlet
        try:
            print("🚀 Starting server with Eventlet...")
            socketio.run(
                app,
                host=host,
                port=port,
                debug=debug_mode,
                use_reloader=debug_mode
            )
        except TypeError as e:
            if 'allow_unsafe_werkzeug' in str(e):
                print("⚠️  Eventlet parameter error, trying without allow_unsafe_werkzeug...")
                socketio.run(
                    app,
                    host=host,
                    port=port,
                    debug=debug_mode,
                    use_reloader=debug_mode,
                    allow_unsafe_werkzeug=False
                )
            else:
                raise e
                
    except ImportError:
        print("⚠️  Eventlet not found, using Flask development server...")
        print("📌 For production, install eventlet: pip install eventlet")
        app.run(
            host=host,
            port=port,
            debug=debug_mode
        )
    except Exception as e:
        print(f"❌ Error starting server: {str(e)}")
        print("🔄 Falling back to Flask development server...")
        app.run(
            host=host,
            port=port,
            debug=debug_mode
        )