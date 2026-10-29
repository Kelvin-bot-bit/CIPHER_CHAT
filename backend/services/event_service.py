# backend/services/event_service.py
"""
Writes ``SystemEvent`` rows and caches small user snapshots.

All writes go through their *own* short-lived database session rather than
``db.session``. That keeps observability from interfering with the request's
transaction (it must never commit someone else's half-finished work, nor be
rolled back by it) and lets us record a server error even when the request's
own session is in a failed state.
"""
import logging
import time

from flask import has_request_context, request, g
from sqlalchemy.orm import Session

from extensions import db
from services.telemetry import telemetry
from utils.redact import redact
from utils.request_info import client_ip, current_request_id

logger = logging.getLogger(__name__)

_throttle = {}
_user_cache = {}
USER_CACHE_TTL = 300


class suppress_telemetry:
    """Context manager: queries inside are not counted as application load."""

    def __enter__(self):
        self._prev = getattr(telemetry.suppress, 'on', False)
        telemetry.suppress.on = True

    def __exit__(self, *exc):
        telemetry.suppress.on = self._prev


def independent_session():
    return Session(db.engine, expire_on_commit=False)


def user_snapshot(user_id):
    """{'username','email','is_admin'} for a user id, cached for a few minutes."""
    if not user_id:
        return None
    now = time.time()
    hit = _user_cache.get(user_id)
    if hit and now - hit[0] < USER_CACHE_TTL:
        return hit[1]
    from models.user import User
    try:
        with suppress_telemetry(), independent_session() as s:
            u = s.get(User, user_id)
            snap = {'username': u.username, 'email': u.email, 'is_admin': bool(u.is_admin)} if u else None
    except Exception:
        return None
    if len(_user_cache) > 2000:
        _user_cache.clear()
    _user_cache[user_id] = (now, snap)
    return snap


def forget_user(user_id):
    _user_cache.pop(user_id, None)


def record_event(level, category, event, message=None, throttle_key=None, throttle_seconds=0, **fields):
    """
    Persist a notable system event. Never raises.

    ``throttle_key``/``throttle_seconds`` collapse floods (e.g. one slow
    endpoint hit 500 times a minute produces one row, not 500).
    """
    from models.monitoring import SystemEvent
    try:
        if throttle_key and throttle_seconds:
            now = time.time()
            last = _throttle.get(throttle_key)
            if last and now - last < throttle_seconds:
                return None
            _throttle[throttle_key] = now
            if len(_throttle) > 5000:
                for k in [k for k, v in _throttle.items() if now - v > 3600]:
                    _throttle.pop(k, None)

        if has_request_context():
            fields.setdefault('request_id', current_request_id())
            fields.setdefault('ip_address', client_ip())
            fields.setdefault('method', request.method)
            fields.setdefault('path', request.path[:255])
            fields.setdefault('user_id', getattr(g, 'log_user_id', None))
            fields.setdefault('username', getattr(g, 'log_username', None))

        details = fields.pop('details', None)
        row = SystemEvent(
            level=level, category=category, event=event,
            message=(message or '')[:500] or None,
            details=redact(details) if details else None,
            **{k: v for k, v in fields.items() if hasattr(SystemEvent, k) and v is not None}
        )
        with suppress_telemetry(), independent_session() as s:
            s.add(row)
            s.commit()
        return row
    except Exception as exc:  # pragma: no cover - last-resort guard
        logger.debug('Could not persist system event %s/%s: %s', category, event, exc)
        return None


def purge_old_records(retention_days):
    """Delete persisted events and resolved alerts past the retention window."""
    from datetime import datetime, timedelta
    from models.monitoring import SystemEvent, Alert
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    try:
        with suppress_telemetry(), independent_session() as s:
            e = s.query(SystemEvent).filter(SystemEvent.created_at < cutoff).delete(synchronize_session=False)
            a = s.query(Alert).filter(Alert.status == 'resolved', Alert.resolved_at < cutoff) \
                .delete(synchronize_session=False)
            s.commit()
        if e or a:
            logger.info('Retention: purged %s system events and %s resolved alerts older than %s days',
                        e, a, retention_days)
    except Exception as exc:
        logger.warning('Retention purge failed: %s', exc)
