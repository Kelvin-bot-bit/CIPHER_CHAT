# backend/utils/logger.py
"""
Structured logging.

* ``logs/app.log``     JSON lines, INFO and above
* ``logs/error.log``   JSON lines, ERROR and above (with stack traces)
* ``logs/access.log``  JSON lines, one per HTTP request (see middleware/observability.py)
* console              human-readable
* admin dashboard      a bounded in-memory ring buffer (services/telemetry.py)

Every record carries the request id and the authenticated user (when there is
one), so a single request can be followed across log lines, the audit trail
and the dashboard. Secrets are redacted before anything is written.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from flask import has_request_context, request, g

from utils.redact import redact

_STD_ATTRS = set(logging.LogRecord('', 0, '', 0, '', (), None).__dict__) | {
    'message', 'asctime', 'request_id', 'user_id', 'username', 'fields', 'taskName'}

ACCESS_LOGGER = 'access'


def _utc_iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class ContextFilter(logging.Filter):
    """Stamps request id / user onto every record emitted during a request."""

    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = getattr(g, 'request_id', None) if has_request_context() else None
        if not hasattr(record, 'user_id'):
            record.user_id = getattr(g, 'log_user_id', None) if has_request_context() else None
            record.username = getattr(g, 'log_username', None) if has_request_context() else None
        return True


class DropSQLEcho(logging.Filter):
    """
    Keeps library chatter out of the log files and the admin dashboard.

    * SQLAlchemy's ``echo`` writes every statement *with its bound parameters*
      (e-mail addresses, password hashes, message ciphertext) at INFO level.
    * engine.io / socket.io log every protocol packet, and werkzeug repeats
      each request line that the access log already records.
    Warnings and errors from all of them still come through. The console is
    untouched, so developers who asked for SQL echo still see it there.
    """

    NOISY = ('sqlalchemy', 'engineio', 'socketio', 'werkzeug')

    def filter(self, record):
        return not (record.name.startswith(self.NOISY) and record.levelno < logging.WARNING)


class JSONFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record):
        data = {
            'timestamp': _utc_iso(record.created),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        rid = getattr(record, 'request_id', None)
        if rid:
            data['request_id'] = rid
        if getattr(record, 'user_id', None):
            data['user_id'] = record.user_id
            data['username'] = getattr(record, 'username', None)
        fields = getattr(record, 'fields', None)
        if fields:
            data.update(redact(fields))
        if record.exc_info:
            data['exception'] = self.formatException(record.exc_info)
        if has_request_context():
            try:
                data['request'] = {
                    'method': request.method,
                    'path': request.path,
                    'ip': request.remote_addr,
                }
            except Exception:  # pragma: no cover
                pass
        return json.dumps(data, default=str)


class RingBufferHandler(logging.Handler):
    """Feeds the admin dashboard's live log view."""

    def __init__(self, telemetry, level=logging.INFO):
        super().__init__(level)
        self.telemetry = telemetry

    def emit(self, record):
        try:
            rec = {
                't': record.created,
                'ts': _utc_iso(record.created),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage()[:2000],
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'request_id': getattr(record, 'request_id', None),
                'user_id': getattr(record, 'user_id', None),
                'username': getattr(record, 'username', None),
                'exception': self._exc(record),
            }
            fields = getattr(record, 'fields', None)
            if fields:
                rec['fields'] = redact(fields)
            self.telemetry.record_log(rec)
        except Exception:  # never let logging break the app
            pass

    @staticmethod
    def _exc(record):
        if not record.exc_info:
            return None
        text = logging.Formatter().formatException(record.exc_info)
        return text[:6000]


_configured = False


def setup_logging(app=None):
    """Configure logging once per process (safe to call repeatedly)."""
    global _configured
    from services.telemetry import telemetry

    cfg = app.config if app is not None else {}
    level_name = str(cfg.get('LOG_LEVEL', os.environ.get('LOG_LEVEL', 'INFO'))).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir = cfg.get('LOG_DIR', 'logs')
    telemetry.configure(request_ring=cfg.get('REQUEST_RING_SIZE'), log_ring=cfg.get('LOG_RING_SIZE'))

    root = logging.getLogger()
    if _configured:
        root.setLevel(min(level, logging.INFO))
        return root

    try:
        os.makedirs(log_dir, exist_ok=True)
        files_ok = True
    except OSError:
        files_ok = False

    root.setLevel(min(level, logging.INFO))
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    ctx = ContextFilter()
    json_fmt = JSONFormatter()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    console.addFilter(ctx)
    root.addHandler(console)

    ring = RingBufferHandler(telemetry, level=logging.INFO)
    ring.addFilter(ctx)
    ring.addFilter(DropSQLEcho())
    root.addHandler(ring)

    if files_ok:
        def _file(name, lvl):
            h = RotatingFileHandler(os.path.join(log_dir, name), maxBytes=10 * 1024 * 1024,
                                    backupCount=10, encoding='utf-8')
            h.setLevel(lvl)
            h.setFormatter(json_fmt)
            h.addFilter(ctx)
            h.addFilter(DropSQLEcho())
            return h

        root.addHandler(_file('app.log', logging.INFO))
        root.addHandler(_file('error.log', logging.ERROR))

        # Access log: its own file, not mixed into app.log.
        access = logging.getLogger(ACCESS_LOGGER)
        access.setLevel(logging.INFO)
        access.propagate = False
        access.handlers = []
        ah = RotatingFileHandler(os.path.join(log_dir, 'access.log'), maxBytes=10 * 1024 * 1024,
                                 backupCount=10, encoding='utf-8')
        ah.setFormatter(json_fmt)
        ah.addFilter(ctx)
        access.addHandler(ah)

    for noisy in ('werkzeug', 'sqlalchemy', 'socketio', 'engineio', 'apscheduler'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if app is not None:
        app.logger.handlers = []
        app.logger.propagate = True
        app.logger.setLevel(level)

    _configured = True
    return root


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name) if name else logging.getLogger()


def _req_ctx(include_body=False):
    if not has_request_context():
        return None
    ctx = {'method': request.method, 'path': request.path, 'ip': request.remote_addr,
           'user_agent': request.headers.get('User-Agent')}
    if include_body:
        body = request.get_json(silent=True)
        if body is not None:
            ctx['body'] = redact(body)
    return ctx


def log_request():
    """Log request details"""
    get_logger().info(f"Request: {request.method} {request.path} - IP: {request.remote_addr}")


def log_error(error: Exception, context: dict = None):
    """Log an error with context (request bodies are redacted)."""
    fields = {'error': str(error), 'error_type': error.__class__.__name__}
    if context:
        fields['context'] = context
    rc = _req_ctx(include_body=True)
    if rc:
        fields['request'] = rc
    get_logger().error(f"{error.__class__.__name__}: {error}", exc_info=True, extra={'fields': fields})


def _log(level, message, context=None):
    fields = {}
    if context:
        fields['context'] = context
    get_logger().log(level, message, extra={'fields': fields} if fields else None)


def log_info(message: str, context: dict = None):
    _log(logging.INFO, message, context)


def log_warning(message: str, context: dict = None):
    _log(logging.WARNING, message, context)


def log_debug(message: str, context: dict = None):
    _log(logging.DEBUG, message, context)


def log_security_event(action: str, user_id: int = None, details: dict = None):
    """Log security-related events"""
    fields = {'action': action, 'category': 'security'}
    if user_id:
        fields['user_id'] = user_id
    if details:
        fields['details'] = details
    if has_request_context():
        fields['ip'] = request.remote_addr
    get_logger('security').warning(f"security: {action}", extra={'fields': fields})


class LoggerMiddleware:
    """WSGI middleware (kept for backwards compatibility)."""

    def __init__(self, app):
        self.app = app
        self.logger = get_logger()

    def __call__(self, environ, start_response):
        self.logger.info(f"Request: {environ.get('REQUEST_METHOD', '')} {environ.get('PATH_INFO', '')}")
        return self.app(environ, start_response)
