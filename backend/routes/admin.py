# backend/routes/admin.py
import csv
import io
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from sqlalchemy.orm import contains_eager

from extensions import db
from models import AuditLog, Group, LoginHistory, Message, User
from models.audit import iso_utc, user_summary
from services.user_service import UserService
from utils.redact import parse_json_details

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


def admin_required(f):
    """
    Decorator to check if user is admin. Refused attempts are logged and
    recorded as security events (someone probing admin endpoints is worth
    knowing about).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if not user or not user.is_admin:
            from services.event_service import record_event
            logger.warning('Admin endpoint refused for user %s: %s %s', user_id, request.method, request.path,
                           extra={'fields': {'category': 'security'}})
            record_event('WARNING', 'security', 'admin_access_denied',
                         f'{user.username if user else user_id} tried {request.method} {request.path}',
                         throttle_key=f'denied:{user_id}', throttle_seconds=60)
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def _sensitive_alert(kind, title, message, details=None):
    """Raise a dashboard alert for a sensitive admin action (never raises)."""
    try:
        from services import alert_service
        alert_service.raise_alert('admin_change', 'warning', title, message,
                                  fingerprint=f'admin_change:{kind}:{int(datetime.utcnow().timestamp())}',
                                  details=details)
    except Exception:  # pragma: no cover
        pass


def _int(name, default, lo=None, hi=None):
    v = request.args.get(name, default, type=int)
    v = default if v is None else v
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


@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def get_users():
    """
    Get all users (admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
      - name: per_page
        in: query
        type: integer
        default: 20
      - name: search
        in: query
        type: string
    responses:
      200:
        description: Users retrieved
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search')
        
        query = User.query
        
        if search:
            query = query.filter(
                User.username.ilike(f'%{search}%') |
                User.email.ilike(f'%{search}%') |
                User.full_name.ilike(f'%{search}%')
            )
        
        pagination = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page
        )
        
        return jsonify({
            'users': [u.to_dict(include_private=True) for u in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }), 200
        
    except Exception as e:
        logger.error(f"Get users error: {str(e)}")
        return jsonify({'error': 'Failed to get users'}), 500

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_user(user_id):
    """
    Update user (admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: user_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            is_active:
              type: boolean
            is_suspended:
              type: boolean
            is_admin:
              type: boolean
            full_name:
              type: string
    responses:
      200:
        description: User updated successfully
    """
    try:
        data = request.get_json(silent=True) or {}
        user = db.session.get(User, user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Prevent admin from removing own admin privileges
        if user_id == int(get_jwt_identity()) and data.get('is_admin') == False:
            return jsonify({'error': 'Cannot remove your own admin privileges'}), 400
        
        # Apply and record exactly what changed (old -> new)
        changes = {}
        for field in ('is_active', 'is_suspended', 'is_admin', 'full_name'):
            if field in data and getattr(user, field) != data[field]:
                changes[field] = {'from': getattr(user, field), 'to': data[field]}
                setattr(user, field, data[field])
        
        db.session.commit()
        
        AuditLog.log_action(
            user_id=int(get_jwt_identity()),
            action='admin_update_user',
            resource_type='user',
            resource_id=user_id,
            resource_label=user.username,
            details={'target': {'username': user.username, 'email': user.email}, 'changes': changes}
        )
        
        if 'is_admin' in changes:
            verb = 'granted' if changes['is_admin']['to'] else 'revoked'
            _sensitive_alert(f'admin_{verb}:{user_id}', f'Admin rights {verb}',
                             f'Admin rights were {verb} for "{user.username}" by user #{get_jwt_identity()}.',
                             {'target_user_id': user_id, 'target_username': user.username})
        if changes.get('is_suspended', {}).get('to') is True:
            logger.warning('User %s suspended by admin %s', user.username, get_jwt_identity())
        
        return jsonify({
            'message': 'User updated successfully',
            'user': user.to_dict(include_private=True)
        }), 200
        
    except Exception as e:
        logger.error(f"Update user error: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to update user'}), 500

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_user(user_id):
    """
    Delete user (admin only)
    ---
    tags:
      - Admin
    parameters:
      - name: user_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: User deleted successfully
    """
    try:
        current_user_id = int(get_jwt_identity())
        
        if user_id == current_user_id:
            return jsonify({'error': 'Cannot delete yourself'}), 400
        
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Capture who this was *before* it is gone, so the audit trail still
        # says "deleted alice (alice@example.com)" rather than "user #12".
        deleted = {'username': user.username, 'email': user.email, 'full_name': user.full_name,
                   'was_admin': bool(user.is_admin)}
        
        db.session.delete(user)
        db.session.commit()
        
        from services.event_service import forget_user
        forget_user(user_id)
        
        AuditLog.log_action(
            user_id=current_user_id,
            action='admin_delete_user',
            resource_type='user',
            resource_id=user_id,
            resource_label=deleted['username'],
            details={'target': deleted}
        )
        _sensitive_alert(f'delete_user:{user_id}', 'User account deleted',
                         f'"{deleted["username"]}" was deleted by user #{current_user_id}.', deleted)
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        logger.error(f"Delete user error: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Failed to delete user'}), 500

@admin_bp.route('/statistics', methods=['GET'])
@jwt_required()
@admin_required
def get_statistics():
    """
    Get system statistics (admin only)
    ---
    tags:
      - Admin
    responses:
      200:
        description: Statistics retrieved
    """
    try:
        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        online_users = User.query.filter_by(online_status='online').count()
        suspended_users = User.query.filter_by(is_suspended=True).count()
        
        # Message statistics
        total_messages = Message.query.count()
        messages_today = Message.query.filter(
            Message.created_at >= db.func.date(db.func.now())
        ).count()
        
        # Group statistics
        total_groups = Group.query.filter_by(is_active=True).count()
        
        # Login statistics
        login_attempts = LoginHistory.query.count()
        failed_logins = LoginHistory.query.filter_by(success=False).count()
        # (the old `.distinct(col).count()` ignored the column on MySQL and
        # simply counted every row)
        unique_users_logged_in = db.session.query(
            func.count(func.distinct(LoginHistory.user_id))
        ).filter(LoginHistory.success == True).scalar()  # noqa: E712
        day_ago = datetime.utcnow() - timedelta(hours=24)
        failed_24h = LoginHistory.query.filter(
            LoginHistory.success == False, LoginHistory.login_time >= day_ago).count()  # noqa: E712
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'online': online_users,
                'suspended': suspended_users
            },
            'messages': {
                'total': total_messages,
                'today': messages_today
            },
            'groups': {
                'total': total_groups
            },
            'login': {
                'total_attempts': login_attempts,
                'failed_attempts': failed_logins,
                'unique_users': unique_users_logged_in,
                'failed_24h': failed_24h
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Get statistics error: {str(e)}")
        return jsonify({'error': 'Failed to get statistics'}), 500

@admin_bp.route('/analytics', methods=['GET'])
@jwt_required()
@admin_required
def get_analytics():
    """
    Time-series activity data for dashboard charts (admin only).
    Bucketed in Python rather than with DB-specific date-truncation SQL,
    so this works the same regardless of the underlying database engine.
    ---
    tags:
      - Admin
    parameters:
      - name: days
        in: query
        type: integer
        default: 14
        description: How many days of history to include (max 90)
    responses:
      200:
        description: Analytics retrieved
    """
    try:
        days = min(request.args.get('days', 14, type=int), 90)
        since = datetime.utcnow() - timedelta(days=days - 1)
        since_start = since.replace(hour=0, minute=0, second=0, microsecond=0)

        # Build the date buckets up front so days with zero activity still
        # show up as 0 instead of being missing from the series entirely
        # (which would otherwise make a line chart's x-axis gap oddly).
        date_keys = [(since_start + timedelta(days=i)).date().isoformat() for i in range(days)]
        messages_by_day = {d: 0 for d in date_keys}
        signups_by_day = {d: 0 for d in date_keys}

        messages = Message.query.filter(
            Message.created_at >= since_start, Message.is_deleted == False
        ).all()
        for m in messages:
            key = m.created_at.date().isoformat()
            if key in messages_by_day:
                messages_by_day[key] += 1

        signups = User.query.filter(User.created_at >= since_start).all()
        for u in signups:
            key = u.created_at.date().isoformat()
            if key in signups_by_day:
                signups_by_day[key] += 1

        user_status_breakdown = {
            'active': User.query.filter_by(is_active=True, is_suspended=False).count(),
            'suspended': User.query.filter_by(is_suspended=True).count(),
            'inactive': User.query.filter_by(is_active=False).count(),
        }

        message_type_breakdown = {}
        for message_type, count in db.session.query(
            Message.message_type, db.func.count(Message.id)
        ).filter(Message.is_deleted == False).group_by(Message.message_type).all():
            message_type_breakdown[message_type or 'text'] = count

        return jsonify({
            'messages_per_day': [{'date': d, 'count': messages_by_day[d]} for d in date_keys],
            'signups_per_day': [{'date': d, 'count': signups_by_day[d]} for d in date_keys],
            'user_status_breakdown': user_status_breakdown,
            'message_type_breakdown': message_type_breakdown,
            'login_success_vs_failed': {
                'success': LoginHistory.query.filter_by(success=True).count(),
                'failed': LoginHistory.query.filter_by(success=False).count(),
            }
        }), 200

    except Exception as e:
        logger.error(f"Get analytics error: {str(e)}")
        return jsonify({'error': 'Failed to get analytics'}), 500

def _audit_query():
    """The audit-log query for the filters in the current request."""
    q = (AuditLog.query
         .outerjoin(User, AuditLog.user_id == User.id)
         .options(contains_eager(AuditLog.user)))

    user_id = request.args.get('user_id', type=int)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)

    action = request.args.get('action')
    if action:
        q = q.filter(AuditLog.action == action) if not action.endswith('*') \
            else q.filter(AuditLog.action.like(action[:-1] + '%'))

    status = request.args.get('status')
    if status in ('success', 'failure'):
        q = q.filter(AuditLog.status == status)

    for col in ('resource_type', 'ip_address', 'request_id'):
        v = request.args.get(col if col != 'ip_address' else 'ip')
        if v:
            q = q.filter(getattr(AuditLog, col) == v)

    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        q = q.filter(
            AuditLog.actor_username.ilike(like) | AuditLog.actor_email.ilike(like)
            | AuditLog.action.ilike(like) | AuditLog.resource_label.ilike(like)
            | AuditLog.ip_address.ilike(like)
            | User.username.ilike(like) | User.email.ilike(like) | User.full_name.ilike(like))

    start, end = _parse_dt(request.args.get('from')), _parse_dt(request.args.get('to'))
    if start:
        q = q.filter(AuditLog.created_at >= start)
    if end:
        q = q.filter(AuditLog.created_at <= end)
    return q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


def _targets_for(rows):
    """Resolve the user an admin action was performed ON (live details if they still exist)."""
    ids = {r.resource_id for r in rows if r.resource_type == 'user' and r.resource_id}
    users = {u.id: u for u in User.query.filter(User.id.in_(ids)).all()} if ids else {}
    out = {}
    for r in rows:
        if r.resource_type != 'user' or not r.resource_id:
            continue
        u = users.get(r.resource_id)
        info = user_summary(u, snapshot_username=r.resource_label, user_id=r.resource_id)
        out[r.id] = info
    return out


@admin_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
@admin_required
def get_audit_logs():
    """
    Audit trail (admin only)

    Every entry names the acting user (username, full name, e-mail, role and
    whether the account still exists), the affected account for user-targeted
    actions, the originating IP/device, and - for failures - the reason.
    Filters: user_id, q (name/e-mail/IP/action), action (``prefix*`` ok),
    status, resource_type, ip, request_id, from, to.
    """
    try:
        page = _int('page', 1, 1)
        per_page = _int('per_page', 50, 1, 200)
        pagination = _audit_query().paginate(page=page, per_page=per_page, error_out=False)
        targets = _targets_for(pagination.items)
        return jsonify({
            'logs': [log.to_dict(target=targets.get(log.id)) for log in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }), 200
    except Exception as e:
        logger.error(f"Get audit logs error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get audit logs'}), 500


@admin_bp.route('/audit-logs/actions', methods=['GET'])
@jwt_required()
@admin_required
def get_audit_actions():
    """Distinct actions with counts (feeds the filter dropdown)."""
    rows = db.session.query(AuditLog.action, func.count(AuditLog.id)) \
        .group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).all()
    return jsonify({'actions': [{'action': a, 'count': c} for a, c in rows]}), 200


@admin_bp.route('/audit-logs/export', methods=['GET'])
@jwt_required()
@admin_required
def export_audit_logs():
    """CSV export of the filtered audit trail (max 5000 rows)."""
    rows = _audit_query().limit(5000).all()
    targets = _targets_for(rows)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['time_utc', 'user_id', 'username', 'full_name', 'email', 'action', 'status', 'reason',
                'resource_type', 'resource_id', 'resource', 'ip_address', 'device', 'request_id', 'details'])
    for r in rows:
        d = r.to_dict(target=targets.get(r.id))
        u = d.get('user') or {}
        details = d.get('details')
        reason = details.get('reason') if isinstance(details, dict) else ''
        t = d.get('target') or {}
        w.writerow([d['created_at'], d['user_id'], u.get('username'), u.get('full_name'), u.get('email'),
                    d['action'], d['status'], reason, d['resource_type'], d['resource_id'],
                    t.get('username') or d['resource_label'], d['ip_address'], d['device'], d['request_id'],
                    details])
    AuditLog.log_action(int(get_jwt_identity()), 'admin_export_audit_logs', 'audit_log',
                        details={'rows': len(rows), 'filters': dict(request.args)})
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=audit-logs.csv'})


# ------------------------------------------------------------ login attempts
def _login_query():
    q = (LoginHistory.query
         .outerjoin(User, LoginHistory.user_id == User.id)
         .options(contains_eager(LoginHistory.user)))
    outcome = request.args.get('outcome')
    if outcome == 'failed':
        q = q.filter(LoginHistory.success == False)  # noqa: E712
    elif outcome == 'success':
        q = q.filter(LoginHistory.success == True)  # noqa: E712
    code = request.args.get('failure_code')
    if code:
        q = q.filter(LoginHistory.failure_code == code)
    ip = request.args.get('ip')
    if ip:
        q = q.filter(LoginHistory.ip_address == ip)
    uid = request.args.get('user_id', type=int)
    if uid:
        q = q.filter(LoginHistory.user_id == uid)
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        q = q.filter(LoginHistory.identifier.ilike(like) | LoginHistory.ip_address.ilike(like)
                     | User.username.ilike(like) | User.email.ilike(like) | User.full_name.ilike(like))
    start, end = _parse_dt(request.args.get('from')), _parse_dt(request.args.get('to'))
    if start:
        q = q.filter(LoginHistory.login_time >= start)
    if end:
        q = q.filter(LoginHistory.login_time <= end)
    return q.order_by(LoginHistory.login_time.desc(), LoginHistory.id.desc())


@admin_bp.route('/login-attempts', methods=['GET'])
@jwt_required()
@admin_required
def get_login_attempts():
    """
    Every login attempt with who it was, where from and - for failures - why.
    Filters: outcome (failed|success), failure_code, ip, user_id, q, from, to.
    """
    try:
        page = _int('page', 1, 1)
        per_page = _int('per_page', 50, 1, 200)
        pagination = _login_query().paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({
            'attempts': [a.to_dict() for a in pagination.items],
            'total': pagination.total, 'page': page, 'per_page': per_page, 'pages': pagination.pages,
            'reasons': LoginHistory.FAILURE_LABELS,
        }), 200
    except Exception as e:
        logger.error(f"Get login attempts error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get login attempts'}), 500


@admin_bp.route('/login-attempts/summary', methods=['GET'])
@jwt_required()
@admin_required
def get_login_summary():
    """Aggregates: failures by reason, noisiest IPs/accounts, locked accounts, hourly trend."""
    try:
        from flask import current_app
        hours = _int('hours', 24, 1, 168)
        since = datetime.utcnow() - timedelta(hours=hours)
        rows = (LoginHistory.query.filter(LoginHistory.login_time >= since)
                .order_by(LoginHistory.login_time.asc()).all())

        by_reason, ips, idents = {}, {}, {}
        trend = {}
        start = since.replace(minute=0, second=0, microsecond=0)
        for i in range(hours + 1):
            trend[(start + timedelta(hours=i)).isoformat() + 'Z'] = {'success': 0, 'failed': 0}
        ok = failed = 0
        for r in rows:
            key = r.login_time.replace(minute=0, second=0, microsecond=0).isoformat() + 'Z'
            bucket = trend.setdefault(key, {'success': 0, 'failed': 0})
            if r.success:
                ok += 1
                bucket['success'] += 1
                continue
            failed += 1
            bucket['failed'] += 1
            code = r.failure_code or 'unknown'
            by_reason[code] = by_reason.get(code, 0) + 1
            if r.ip_address:
                e = ips.setdefault(r.ip_address, {'ip': r.ip_address, 'failed': 0, 'identifiers': set(), 'last': None})
                e['failed'] += 1
                if r.identifier:
                    e['identifiers'].add(r.identifier.lower())
                e['last'] = r.login_time
            label = (r.identifier or (r.user.username if r.user else None) or 'unknown').lower()
            e = idents.setdefault(label, {'identifier': label, 'failed': 0, 'last': None, 'exists': r.user_id is not None})
            e['failed'] += 1
            e['last'] = r.login_time

        lockout = current_app.config.get('LOCKOUT_TIME', 15)
        max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
        locked = []
        for label, e in idents.items():
            if e['failed'] >= max_attempts:
                counted = LoginHistory.count_recent_failures(identifier=label, minutes=lockout)
                if counted >= max_attempts:
                    locked.append({'identifier': label, 'failed': counted, 'last': iso_utc(e['last']),
                                   'exists': e['exists']})

        return jsonify({
            'hours': hours, 'total': ok + failed, 'success': ok, 'failed': failed,
            'by_reason': [{'code': c, 'label': LoginHistory.FAILURE_LABELS.get(c, c), 'count': n}
                          for c, n in sorted(by_reason.items(), key=lambda x: -x[1])],
            'top_ips': [{'ip': e['ip'], 'failed': e['failed'], 'distinct_accounts': len(e['identifiers']),
                         'last': iso_utc(e['last'])}
                        for e in sorted(ips.values(), key=lambda x: -x['failed'])[:10]],
            'top_accounts': [{'identifier': e['identifier'], 'failed': e['failed'], 'exists': e['exists'],
                              'last': iso_utc(e['last'])}
                             for e in sorted(idents.values(), key=lambda x: -x['failed'])[:10]],
            'locked_accounts': locked,
            'trend': [{'t': k, **v} for k, v in sorted(trend.items())],
        }), 200
    except Exception as e:
        logger.error(f"Login summary error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to build login summary'}), 500


@admin_bp.route('/system-status', methods=['GET'])
@jwt_required()
@admin_required
def get_system_status():
    """
    Quick system status (admin only). The full picture is under
    /api/admin/monitoring/health; this keeps the original response shape.
    """
    try:
        from services import monitoring_service
        health = monitoring_service.run_health_checks()
        db_status = 'connected' if health['checks']['database']['status'] != 'fail' else 'disconnected'

        recent_errors = AuditLog.query.filter_by(status='failure').order_by(
            AuditLog.created_at.desc()
        ).limit(10).all()

        return jsonify({
            'database': db_status,
            'status': health['status'],
            'timestamp': datetime.utcnow().isoformat(),
            'recent_errors': [error.to_dict() for error in recent_errors],
            'server_time': datetime.utcnow().isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Get system status error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get system status'}), 500
