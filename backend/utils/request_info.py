# backend/utils/request_info.py
"""Request-derived facts used by logging, auditing and alerting."""
from flask import current_app, g, has_request_context, request


def client_ip():
    """
    The caller's IP address.

    ``X-Forwarded-For`` is only honoured when TRUST_PROXY_HEADERS is enabled
    (i.e. the app really sits behind a reverse proxy that sets it). Trusting
    it unconditionally would let anyone spoof their IP in the audit trail and
    dodge IP-based brute-force detection.
    """
    if not has_request_context():
        return None
    try:
        trust = current_app.config.get('TRUST_PROXY_HEADERS', False)
    except RuntimeError:
        trust = False
    if trust:
        fwd = request.headers.get('X-Forwarded-For')
        if fwd:
            return fwd.split(',')[0].strip()[:45]
    return (request.remote_addr or '')[:45] or None


def current_request_id():
    if has_request_context():
        return getattr(g, 'request_id', None)
    return None


def current_user_agent():
    if has_request_context():
        return request.headers.get('User-Agent')
    return None
