# backend/middleware/observability.py
"""
Per-request observability.

For every HTTP request this:
* assigns a request id (honouring a sane incoming ``X-Request-ID``) and returns
  it as a response header, so a user-reported problem can be traced end to end
* measures response time and counts/times the database queries it triggered
* writes a structured line to ``logs/access.log`` and feeds the live
  dashboard (request ring buffer, per-minute metrics)
* persists notable events (5xx, slow requests, rate limiting) to the database
* records every authenticated write (POST/PUT/PATCH/DELETE) in the audit trail
  automatically, unless the handler already wrote a specific audit entry
* captures unhandled exceptions with a stack trace and raises an alert
"""
import logging
import re
import time
import traceback
import uuid

from flask import g, request, has_request_context
from sqlalchemy import event
from sqlalchemy.engine import Engine

from extensions import db
from services.telemetry import telemetry
from utils.logger import ACCESS_LOGGER
from utils.request_info import client_ip
from utils.redact import redact, safe_path

logger = logging.getLogger(__name__)
access_logger = logging.getLogger(ACCESS_LOGGER)

_RID = re.compile(r'^[A-Za-z0-9._-]{8,64}$')
_MUTATING = {'POST', 'PUT', 'PATCH', 'DELETE'}
# Endpoints that are either audited explicitly or are pure noise.
_AUDIT_SKIP_ENDPOINTS = {'auth.refresh', 'auth.login', 'auth.register', 'auth.logout'}
_AUDIT_SKIP_PREFIXES = ('push.', 'static')
_INTERNAL_PREFIX = '/api/admin/monitoring'

_listeners_installed = False


# --------------------------------------------------------- database timing
def install_query_listeners(app):
    """Time every SQL statement (engine-wide, installed once per process)."""
    global _listeners_installed
    if _listeners_installed:
        return
    _listeners_installed = True

    @event.listens_for(Engine, 'before_cursor_execute')
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault('_q_start', []).append(time.perf_counter())

    @event.listens_for(Engine, 'after_cursor_execute')
    def _after(conn, cursor, statement, parameters, context, executemany):
        stack = conn.info.get('_q_start')
        if not stack:
            return
        ms = (time.perf_counter() - stack.pop()) * 1000.0
        if getattr(telemetry.suppress, 'on', False):
            return
        threshold = app.config.get('SLOW_QUERY_MS', 500)
        slow = ms >= threshold
        rid = None
        if has_request_context():
            g.db_n = getattr(g, 'db_n', 0) + 1
            g.db_ms = getattr(g, 'db_ms', 0.0) + ms
            rid = getattr(g, 'request_id', None)
        stmt = ' '.join(statement.split())[:400] if slow else None
        telemetry.record_query(stmt, ms, slow, request_id=rid)
        if slow:
            logger.warning('Slow query (%.0f ms): %s', ms, stmt,
                           extra={'fields': {'duration_ms': round(ms, 1), 'category': 'database'}})

    @event.listens_for(Engine, 'handle_error')
    def _error(ctx):
        stack = ctx.connection.info.get('_q_start') if ctx.connection is not None else None
        if stack:
            stack.pop()
        telemetry.record_query_error()


# -------------------------------------------------------------- user lookup
def _identify_user(optional_verify=False):
    """Best-effort: who is making this request (never raises, never blocks)."""
    uid = getattr(g, 'log_user_id', None)
    if uid:
        return uid
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
        if optional_verify:
            verify_jwt_in_request(optional=True)
        ident = get_jwt_identity()
        if ident is not None:
            g.log_user_id = int(ident)
            from services.event_service import user_snapshot
            snap = user_snapshot(g.log_user_id)
            g.log_username = snap['username'] if snap else None
    except Exception:
        pass
    return getattr(g, 'log_user_id', None)


# ------------------------------------------------------------ audit trail
def _audit_api_activity(response, ms):
    from models.audit import AuditLog
    from services.event_service import suppress_telemetry, user_snapshot
    endpoint = request.endpoint or ''
    if endpoint in _AUDIT_SKIP_ENDPOINTS or endpoint.startswith(_AUDIT_SKIP_PREFIXES):
        return
    uid = g.log_user_id
    snap = user_snapshot(uid) or {}
    view_args = request.view_args or {}
    rid = next((v for v in view_args.values() if isinstance(v, int)), None)
    status = 'success' if response.status_code < 400 else 'failure'
    details = {'method': request.method, 'path': request.path, 'status_code': response.status_code,
               'duration_ms': round(ms, 1)}
    if response.status_code >= 400:
        details['error'] = _error_text(response)
    try:
        with suppress_telemetry(), db.engine.begin() as conn:
            conn.execute(AuditLog.__table__.insert().values(
                user_id=uid, actor_username=snap.get('username'), actor_email=snap.get('email'),
                action=endpoint or f'{request.method} {request.path}'[:100],
                resource_type=(request.blueprint or None), resource_id=rid,
                ip_address=client_ip(), user_agent=request.headers.get('User-Agent'),
                request_id=getattr(g, 'request_id', None), details=redact(details), status=status))
    except Exception as exc:
        logger.debug('API activity audit failed: %s', exc)


def _error_text(response):
    try:
        data = response.get_json(silent=True)
        if isinstance(data, dict):
            return str(data.get('error') or data.get('message') or '')[:200]
    except Exception:
        pass
    return ''


# ------------------------------------------------------------- exceptions
def record_exception(exc):
    """Called by the app's unhandled-exception handler."""
    from services import alert_service
    from services.event_service import record_event
    try:
        tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        g.exception_info = f'{type(exc).__name__}: {exc}'[:300]
        route = request.url_rule.rule if (has_request_context() and request.url_rule) else '(unmatched)'
        logger.error('Unhandled exception on %s %s: %s', request.method, request.path, exc,
                     exc_info=(type(exc), exc, exc.__traceback__),
                     extra={'fields': {'category': 'exception', 'route': route}})
        record_event('ERROR', 'system', 'unhandled_exception', g.exception_info,
                     throttle_key=f'exc:{type(exc).__name__}:{route}', throttle_seconds=30,
                     details={'type': type(exc).__name__, 'route': route, 'traceback': tb[-4000:]})
        alert_service.raise_alert(
            'unhandled_exception', 'critical', f'Unhandled {type(exc).__name__} in {route}',
            f'{request.method} {request.path} crashed: {str(exc)[:300]}',
            fingerprint=f'exception:{type(exc).__name__}:{route}',
            details={'route': route, 'request_id': getattr(g, 'request_id', None), 'traceback': tb[-2500:]})
    except Exception:  # pragma: no cover - must never mask the original error
        pass


# -------------------------------------------------------------------- init
def init_observability(app):
    install_query_listeners(app)

    @app.before_request
    def _obs_before():
        incoming = request.headers.get('X-Request-ID', '')
        g.request_id = (incoming[:36] if _RID.match(incoming or '') else str(uuid.uuid4()))
        g._obs_t0 = time.perf_counter()
        g.db_n = 0
        g.db_ms = 0.0
        if request.method != 'OPTIONS':
            _identify_user(optional_verify=True)

    @app.after_request
    def _obs_after(response):
        try:
            _finish(app, response)
        except Exception as exc:  # observability must never break a response
            logger.debug('observability after_request failed: %s', exc)
        return response


def _finish(app, response):
    t0 = getattr(g, '_obs_t0', None)
    if t0 is None:
        return
    ms = (time.perf_counter() - t0) * 1000.0
    rid = getattr(g, 'request_id', None)
    response.headers['X-Request-ID'] = rid or ''
    response.headers['X-Response-Time'] = f'{ms:.1f}ms'

    if request.method == 'OPTIONS':
        return

    uid = _identify_user()
    status = response.status_code
    route = request.url_rule.rule if request.url_rule else None
    slow = ms >= app.config.get('SLOW_REQUEST_MS', 1000)
    ip = client_ip()
    internal = request.path.startswith(_INTERNAL_PREFIX)
    size = response.calculate_content_length() or 0

    rec = {
        'request_id': rid, 'method': request.method, 'path': safe_path(request.path, request.query_string)[:200],
        'route': route, 'endpoint': request.endpoint, 'status': status, 'ms': round(ms, 2),
        'db_n': getattr(g, 'db_n', 0), 'db_ms': round(getattr(g, 'db_ms', 0.0), 2),
        'user_id': uid, 'username': getattr(g, 'log_username', None), 'ip': ip,
        'ua': (request.headers.get('User-Agent') or '')[:160], 'bytes': size, 'slow': slow,
        'internal': internal, 'error': getattr(g, 'exception_info', None),
    }
    telemetry.record_request(rec)

    level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
    access_logger.log(level, f'{request.method} {request.path} {status} {ms:.0f}ms',
                      extra={'fields': {
                          'method': request.method, 'path': request.path, 'route': route, 'status': status,
                          'duration_ms': round(ms, 2), 'db_queries': rec['db_n'], 'db_ms': rec['db_ms'],
                          'bytes': size, 'ip': ip, 'user_agent': rec['ua'], 'user_id': uid}})

    if internal:
        return

    from services.event_service import record_event
    if status >= 500:
        record_event('ERROR', 'request', 'server_error', f'{request.method} {request.path} -> {status}',
                     throttle_key=f'5xx:{route}:{status}', throttle_seconds=5, status_code=status,
                     duration_ms=ms, user_id=uid, details={'route': route, 'error': rec['error']})
    elif slow:
        logger.warning('Slow request: %s %s took %.0f ms', request.method, request.path, ms,
                       extra={'fields': {'duration_ms': round(ms, 1), 'category': 'performance'}})
        record_event('WARNING', 'request', 'slow_request',
                     f'{request.method} {request.path} took {ms:.0f} ms', throttle_key=f'slow:{route}',
                     throttle_seconds=60, status_code=status, duration_ms=ms, user_id=uid,
                     details={'route': route, 'db_queries': rec['db_n'], 'db_ms': rec['db_ms']})
    elif status == 429:
        record_event('WARNING', 'security', 'rate_limited', f'Rate limit hit on {request.method} {request.path}',
                     throttle_key=f'429:{ip}', throttle_seconds=60, status_code=status)

    if (app.config.get('AUDIT_API_ACTIVITY', True) and request.method in _MUTATING and uid
            and status < 500 and not getattr(g, 'audit_logged', False)):
        _audit_api_activity(response, ms)
