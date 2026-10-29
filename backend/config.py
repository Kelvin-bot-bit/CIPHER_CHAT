# backend/config.py
import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    TESTING = False
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'mysql+pymysql://root:password@localhost/secure_chat_app'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.environ.get('SQL_ECHO', 'False').lower() == 'true'
    SQLALCHEMY_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', 10))
    SQLALCHEMY_POOL_TIMEOUT = int(os.environ.get('DB_POOL_TIMEOUT', 30))
    SQLALCHEMY_POOL_RECYCLE = int(os.environ.get('DB_POOL_RECYCLE', 3600))
    
    # JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 1))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 30))
    )
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = os.environ.get('JWT_COOKIE_SECURE', 'False').lower() == 'true'
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'
    JWT_COOKIE_SAMESITE = 'Lax'
    
    # CORS
    CORS_ORIGINS = os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:3000,http://localhost:5000'
    ).split(',')
    
    # Rate Limiting
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '100 per hour')
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    
    # File Upload
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))  # 100MB
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    # Largest video accepted for a status update (it is encrypted in memory, so
    # this also bounds RAM per upload/view). The web app's composer shows 50 MB.
    STATUS_MAX_VIDEO_MB = int(os.environ.get('STATUS_MAX_VIDEO_MB', 50))
    ALLOWED_EXTENSIONS = {
        'images': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'},
        'documents': {'pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx', 'odt'},
        'videos': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'},
        'audio': {'mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a'},
        'archives': {'zip', 'rar', '7z', 'tar', 'gz'}
    }
    ALLOWED_MIME_TYPES = [
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
        'application/pdf', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'video/mp4', 'video/quicktime', 'video/x-msvideo',
        'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/aac',
        'application/zip', 'application/x-rar-compressed'
    ]
    
    # Email (for verification and notifications)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@securechat.com')
    
    # Web Push (browser push notifications, delivered even when the tab
    # is closed). VAPID_PRIVATE_KEY must be kept secret — it's what proves
    # to the browser's push service that pushes are coming from this
    # server. Generate a real pair per deployment rather than using any
    # default; see services/push_service.py's module docstring for how.
    # Leaving these unset disables push (subscribe attempts return a clear
    # "not configured" error rather than failing silently).
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'admin@example.com')
    
    # Security
    BCRYPT_LOG_ROUNDS = int(os.environ.get('BCRYPT_LOG_ROUNDS', 12))
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    
    # Password Policy
    PASSWORD_MIN_LENGTH = int(os.environ.get('PASSWORD_MIN_LENGTH', 8))
    MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', 5))
    LOCKOUT_TIME = int(os.environ.get('LOCKOUT_TIME', 15))  # minutes
    
    # Encryption
    RSA_KEY_SIZE = int(os.environ.get('RSA_KEY_SIZE', 2048))
    AES_KEY_SIZE = int(os.environ.get('AES_KEY_SIZE', 32))  # 256 bits
    PBKDF2_ITERATIONS = int(os.environ.get('PBKDF2_ITERATIONS', 100000))
    
    # Cache
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
    

    # ------------------------------------------------------------------
    # Monitoring & observability
    # ------------------------------------------------------------------
    # Honour X-Forwarded-For for client IPs (ONLY enable behind a proxy you
    # control; otherwise clients can spoof their IP in audit/login records).
    TRUST_PROXY_HEADERS = os.environ.get('TRUST_PROXY_HEADERS', 'False').lower() == 'true'

    # In-memory ring buffers shown live in the admin dashboard.
    LOG_RING_SIZE = int(os.environ.get('LOG_RING_SIZE', 5000))
    REQUEST_RING_SIZE = int(os.environ.get('REQUEST_RING_SIZE', 10000))
    LOG_DIR = os.environ.get('LOG_DIR', 'logs')

    # Thresholds
    SLOW_REQUEST_MS = int(os.environ.get('SLOW_REQUEST_MS', 1000))
    SLOW_QUERY_MS = int(os.environ.get('SLOW_QUERY_MS', 500))

    # Background health-check / alert evaluation cadence.
    MONITOR_ENABLED = os.environ.get('MONITOR_ENABLED', 'True').lower() == 'true'
    MONITOR_INTERVAL_SECONDS = int(os.environ.get('MONITOR_INTERVAL_SECONDS', 30))

    # Every authenticated write (POST/PUT/PATCH/DELETE) is added to the audit
    # trail automatically, in addition to the explicit audit entries.
    AUDIT_API_ACTIVITY = os.environ.get('AUDIT_API_ACTIVITY', 'True').lower() == 'true'

    # Alert rule thresholds
    ALERT_ERROR_RATE_WARN = float(os.environ.get('ALERT_ERROR_RATE_WARN', 5))    # % of 5xx over 5 min
    ALERT_ERROR_RATE_CRIT = float(os.environ.get('ALERT_ERROR_RATE_CRIT', 15))
    ALERT_MIN_REQUESTS = int(os.environ.get('ALERT_MIN_REQUESTS', 20))           # ignore tiny samples
    ALERT_P95_WARN_MS = int(os.environ.get('ALERT_P95_WARN_MS', 1500))
    ALERT_P95_CRIT_MS = int(os.environ.get('ALERT_P95_CRIT_MS', 4000))
    ALERT_DB_LATENCY_WARN_MS = int(os.environ.get('ALERT_DB_LATENCY_WARN_MS', 250))
    ALERT_DB_POOL_WARN_PCT = int(os.environ.get('ALERT_DB_POOL_WARN_PCT', 90))
    ALERT_SLOW_QUERY_BURST = int(os.environ.get('ALERT_SLOW_QUERY_BURST', 10))   # per 5 min
    ALERT_FAILED_LOGIN_WINDOW_MIN = int(os.environ.get('ALERT_FAILED_LOGIN_WINDOW_MIN', 10))
    ALERT_FAILED_LOGIN_TOTAL = int(os.environ.get('ALERT_FAILED_LOGIN_TOTAL', 15))
    ALERT_FAILED_LOGIN_PER_IP = int(os.environ.get('ALERT_FAILED_LOGIN_PER_IP', 8))
    ALERT_DISTINCT_IDENTIFIERS_PER_IP = int(os.environ.get('ALERT_DISTINCT_IDENTIFIERS_PER_IP', 5))
    ALERT_DISK_FREE_WARN_PCT = float(os.environ.get('ALERT_DISK_FREE_WARN_PCT', 15))
    ALERT_DISK_FREE_CRIT_PCT = float(os.environ.get('ALERT_DISK_FREE_CRIT_PCT', 5))
    ALERT_MEMORY_WARN_PCT = float(os.environ.get('ALERT_MEMORY_WARN_PCT', 85))

    # Notification channels (all optional)
    ALERT_EMAILS = [e.strip() for e in os.environ.get('ALERT_EMAILS', '').split(',') if e.strip()]
    ALERT_EMAIL_MIN_SEVERITY = os.environ.get('ALERT_EMAIL_MIN_SEVERITY', 'critical')  # warning|critical
    ALERT_WEBHOOK_URL = os.environ.get('ALERT_WEBHOOK_URL', '')   # Slack/Teams/Discord-style {"text": ...}
    ALERT_COOLDOWN_SECONDS = int(os.environ.get('ALERT_COOLDOWN_SECONDS', 900))

    # Retention for the persisted event/alert history
    EVENT_RETENTION_DAYS = int(os.environ.get('EVENT_RETENTION_DAYS', 30))

    # Application
    APP_NAME = 'Secure Chat Application'
    APP_VERSION = '1.0.0'
    API_PREFIX = '/api'

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    CACHE_TYPE = 'simple'
    
    # Disable SSL for development
    MAIL_USE_TLS = False
    MAIL_USE_SSL = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ECHO = False
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    
    # Use in-memory cache for testing
    CACHE_TYPE = 'simple'
    
    # Disable SSL for testing
    MAIL_USE_TLS = False
    MAIL_USE_SSL = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SQLALCHEMY_ECHO = False
    JWT_COOKIE_SECURE = True
    RATELIMIT_ENABLED = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    # Stricter CORS for production
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '').split(',')
    
    # Use Redis for rate limiting and caching in production
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'redis://localhost:6379')
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'redis')
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Security
    BCRYPT_LOG_ROUNDS = 14  # Higher for production
    
    # Performance
    SQLALCHEMY_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', 20))
    SQLALCHEMY_POOL_TIMEOUT = int(os.environ.get('DB_POOL_TIMEOUT', 60))
    SQLALCHEMY_POOL_RECYCLE = int(os.environ.get('DB_POOL_RECYCLE', 3600))
    
    # Security headers
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'

# Configuration mapping
config_map = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)