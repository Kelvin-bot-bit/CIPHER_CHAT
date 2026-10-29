# backend/routes/monitoring.py
"""
Admin-only monitoring & observability API (mounted at /api/admin/monitoring).

Live data (requests, logs, latency) comes from the in-memory telemetry store;
history (events, alerts) comes from the database.
"""
import csv
import io
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import Alert, SystemEvent, User
from services import alert_service, monitoring_service
from services.event_service import record_event, suppress_telemetry
from services.telemetry import iso, telemetry

monitoring_bp = Blueprint('monitoring', __name__)
logger = logging.getLogger(__name__)


def admin_only(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = db.session.get(User, int(get_jwt_identity()))
        if not user or not user.is_admin or not user.is_active or user.is_suspended:
            record_event('WARNING', 'security', 'admin_access_denied',
                         'Non-admin attempted to use the monitoring API',
                         throttle_key=f'denied:{get_jwt_identity()}', throttle_seconds=60)
            return jsonify({'error': 'Admin privileges required'}), 403
        request.admin_user = user
        return f(*args, **kwargs)
    return wrapper


def _int(name, default, lo=None, hi=None):
    v = request.args.get(name, default, type=int)
    if v is None:
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


@monitoring_bp.route('/overview', methods=['GET'])
@jwt_required()
@admin_only
def overview():
    """Everything the dashboard header needs in one round trip."""
    minutes = _int('minutes', 60, 5, 1440)
    health = monitoring_service.run_health_checks(force=request.args.get('refresh') == '1')
    db_check = health['checks']['database']
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    from models import LoginHistory
    failed_24h = LoginHistory.query.filter(LoginHistory.success == False,  # noqa: E712
                                           LoginHistory.login_time >= day_ago).count()
    success_24h = LoginHistory.query.filter(LoginHistory.success == True,  # noqa: E712
                                            LoginHistory.login_time >= day_ago).count()
    errors_24h = SystemEvent.query.filter(SystemEvent.level.in_(('ERROR', 'CRITICAL')),
                                          SystemEvent.created_at >= day_ago).count()
    return jsonify({
        'status': health['status'],
        'checked_at': health['checked_at'],
        'uptime_seconds': telemetry.uptime_seconds,
        'live': telemetry.summary(5),
        'window': telemetry.summary(minutes),
        'status_codes': telemetry.status_codes(minutes),
        'database': {'status': db_check['status'], 'latency_ms': db_check.get('latency_ms'),
                     'pool': db_check.get('details', {}).get('pool'),
                     'avg_query_ms': telemetry.summary(minutes)['db_avg_ms']},
        'alerts': alert_service.summary(),
        'security': {'failed_logins_24h': failed_24h, 'successful_logins_24h': success_24h},
        'errors_24h': errors_24h,
        'log_levels': telemetry.log_level_counts(minutes),
        'totals': {'requests': telemetry.requests_total, 'db_queries': telemetry.db_queries_total,
                   'errors_5xx': telemetry.errors_5xx_total, 'db_errors': telemetry.db_errors_total},
    }), 200


@monitoring_bp.route('/health', methods=['GET'])
@jwt_required()
@admin_only
def health():
    return jsonify(monitoring_service.run_health_checks(force=request.args.get('refresh') == '1')), 200


@monitoring_bp.route('/timeseries', methods=['GET'])
@jwt_required()
@admin_only
def timeseries():
    minutes = _int('minutes', 60, 5, 1440)
    points = telemetry.timeseries(minutes)
    if minutes > 180:  # keep payloads and charts small: merge into coarser buckets
        step = 5 if minutes <= 720 else 15
        merged = []
        for i in range(0, len(points), step):
            chunk = points[i:i + step]
            n = sum(p['requests'] for p in chunk)
            avg = [p['avg_ms'] * p['requests'] for p in chunk if p['avg_ms'] is not None]
            p95 = [p['p95_ms'] for p in chunk if p['p95_ms'] is not None]
            merged.append({
                't': chunk[0]['t'], 'requests': n,
                'errors_5xx': sum(p['errors_5xx'] for p in chunk),
                'errors_4xx': sum(p['errors_4xx'] for p in chunk),
                'avg_ms': round(sum(avg) / n, 1) if n else None,
                'p95_ms': max(p95) if p95 else None,
                'max_ms': max((p['max_ms'] for p in chunk if p['max_ms'] is not None), default=None),
                'db_avg_ms': None, 'slow_queries': sum(p['slow_queries'] for p in chunk)})
        points = merged
    return jsonify({'minutes': minutes, 'points': points}), 200


@monitoring_bp.route('/endpoints', methods=['GET'])
@jwt_required()
@admin_only
def endpoints():
    rows = telemetry.endpoint_stats(_int('minutes', 60, 5, 1440), request.args.get('sort', 'p95'),
                                    _int('limit', 30, 1, 100))
    return jsonify({'endpoints': rows, 'sample_size': len(telemetry.requests)}), 200


@monitoring_bp.route('/requests', methods=['GET'])
@jwt_required()
@admin_only
def requests_log():
    items = telemetry.get_requests(
        limit=_int('limit', 100, 1, 500), since_id=request.args.get('since_id', type=int),
        status=request.args.get('status'), method=request.args.get('method'), q=request.args.get('q'),
        user_id=request.args.get('user_id', type=int), min_ms=request.args.get('min_ms', type=float),
        slow=request.args.get('slow') == '1', request_id=request.args.get('request_id'),
        ip=request.args.get('ip'))
    return jsonify({'requests': items, 'latest_id': telemetry._req_seq}), 200


@monitoring_bp.route('/logs', methods=['GET'])
@jwt_required()
@admin_only
def logs():
    items = telemetry.get_logs(
        limit=_int('limit', 200, 1, 1000), since_id=request.args.get('since_id', type=int),
        level=request.args.get('level'), logger=request.args.get('logger'),
        q=request.args.get('q'), request_id=request.args.get('request_id'))
    return jsonify({'logs': items, 'latest_id': telemetry._log_seq,
                    'capacity': telemetry.logs.maxlen}), 200


@monitoring_bp.route('/logs/export', methods=['GET'])
@jwt_required()
@admin_only
def logs_export():
    """Download the in-memory log buffer as newline-delimited JSON."""
    import json
    items = telemetry.get_logs(limit=1000, level=request.args.get('level'), q=request.args.get('q'),
                               request_id=request.args.get('request_id'))
    body = '\n'.join(json.dumps(i, default=str) for i in reversed(items))
    return Response(body, mimetype='application/x-ndjson',
                    headers={'Content-Disposition': 'attachment; filename=app-logs.ndjson'})


@monitoring_bp.route('/slow-queries', methods=['GET'])
@jwt_required()
@admin_only
def slow_queries():
    return jsonify({'queries': telemetry.get_slow_queries(_int('limit', 50, 1, 200)),
                    'threshold_ms': _threshold()}), 200


def _threshold():
    from flask import current_app
    return current_app.config.get('SLOW_QUERY_MS', 500)


@monitoring_bp.route('/events', methods=['GET'])
@jwt_required()
@admin_only
def events():
    """Persisted system events (survive restarts)."""
    q = SystemEvent.query
    level = request.args.get('level')
    if level:
        order = ['INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if level.upper() in order:
            q = q.filter(SystemEvent.level.in_(order[order.index(level.upper()):]))
    for col in ('category', 'event', 'request_id', 'ip_address'):
        v = request.args.get(col)
        if v:
            q = q.filter(getattr(SystemEvent, col) == v)
    uid = request.args.get('user_id', type=int)
    if uid:
        q = q.filter(SystemEvent.user_id == uid)
    term = request.args.get('q')
    if term:
        like = f'%{term}%'
        q = q.filter(SystemEvent.message.ilike(like) | SystemEvent.path.ilike(like)
                     | SystemEvent.event.ilike(like) | SystemEvent.username.ilike(like))
    start, end = _parse_dt(request.args.get('from')), _parse_dt(request.args.get('to'))
    if start:
        q = q.filter(SystemEvent.created_at >= start)
    if end:
        q = q.filter(SystemEvent.created_at <= end)
    page = _int('page', 1, 1)
    per_page = _int('per_page', 50, 1, 200)
    pag = q.order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({'events': [e.to_dict() for e in pag.items], 'total': pag.total, 'page': page,
                    'pages': pag.pages, 'per_page': per_page}), 200


# ----------------------------------------------------------------- alerts
@monitoring_bp.route('/alerts', methods=['GET'])
@jwt_required()
@admin_only
def alerts():
    status = request.args.get('status', 'active')
    q = Alert.query
    if status == 'active':
        q = q.filter(Alert.status != 'resolved')
    elif status in ('open', 'acknowledged', 'resolved'):
        q = q.filter(Alert.status == status)
    sev = request.args.get('severity')
    if sev:
        q = q.filter(Alert.severity == sev)
    page = _int('page', 1, 1)
    per_page = _int('per_page', 25, 1, 100)
    pag = q.order_by(Alert.last_seen.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({'alerts': [a.to_dict() for a in pag.items], 'total': pag.total, 'page': page,
                    'pages': pag.pages, 'summary': alert_service.summary()}), 200


@monitoring_bp.route('/alerts/summary', methods=['GET'])
@jwt_required()
@admin_only
def alerts_summary():
    return jsonify(alert_service.summary()), 200


@monitoring_bp.route('/alerts/rules', methods=['GET'])
@jwt_required()
@admin_only
def alert_rules():
    active = {a['rule'] for a in alert_service.open_alerts()}
    rules = monitoring_service.rule_catalogue()
    for r in rules:
        r['firing'] = r['rule'] in active
    from flask import current_app
    cfg = current_app.config
    return jsonify({
        'rules': rules,
        'channels': {'dashboard': True, 'webhook': bool(cfg.get('ALERT_WEBHOOK_URL')),
                     'email': bool(cfg.get('ALERT_EMAILS') and cfg.get('MAIL_USERNAME')),
                     'email_min_severity': cfg.get('ALERT_EMAIL_MIN_SEVERITY'),
                     'cooldown_seconds': cfg.get('ALERT_COOLDOWN_SECONDS')},
        'evaluation_interval_seconds': cfg.get('MONITOR_INTERVAL_SECONDS'),
    }), 200


@monitoring_bp.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@jwt_required()
@admin_only
def acknowledge(alert_id):
    data = alert_service.acknowledge_alert(alert_id, request.admin_user)
    if not data:
        return jsonify({'error': 'Alert not found'}), 404
    from models import AuditLog
    AuditLog.log_action(request.admin_user.id, 'admin_acknowledge_alert', 'alert', alert_id,
                        resource_label=data['title'])
    return jsonify({'alert': data}), 200


@monitoring_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@jwt_required()
@admin_only
def resolve(alert_id):
    data = alert_service.resolve_alert_by_id(alert_id, request.admin_user)
    if not data:
        return jsonify({'error': 'Alert not found'}), 404
    from models import AuditLog
    AuditLog.log_action(request.admin_user.id, 'admin_resolve_alert', 'alert', alert_id,
                        resource_label=data['title'])
    return jsonify({'alert': data}), 200


@monitoring_bp.route('/alerts/test', methods=['POST'])
@jwt_required()
@admin_only
def test_alert():
    return jsonify({'sent_to': alert_service.send_test_alert(request.admin_user)}), 200
