# backend/services/alert_service.py
"""
Alert lifecycle and notification.

An alert is identified by a *fingerprint* (rule + subject). Raising the same
fingerprint again while the alert is still open just bumps its counter and
timestamp instead of creating duplicates, so one ongoing incident is one
alert. Alerts move open -> acknowledged -> resolved; condition-based alerts
resolve themselves when the condition clears (see monitoring_service).

Notifications (all optional, configured through environment variables):
* the admin dashboard, live over Socket.IO ("admin_alert")
* a webhook (Slack / Teams / Discord style ``{"text": ...}``)
* e-mail via Flask-Mail
Each fingerprint is re-notified at most once per ALERT_COOLDOWN_SECONDS unless
its severity escalates.
"""
import logging
import threading
from datetime import datetime, timedelta

from flask import current_app

from extensions import db, socketio
from models.monitoring import Alert, SEVERITY_RANK
from services.event_service import independent_session, record_event, suppress_telemetry

logger = logging.getLogger(__name__)


def _now():
    return datetime.utcnow()


def raise_alert(rule, severity, title, message, fingerprint=None, details=None, notify=True):
    """Create or refresh an alert. Returns (alert_dict, is_new). Never raises."""
    fingerprint = (fingerprint or rule)[:160]
    try:
        escalated = False
        with suppress_telemetry(), independent_session() as s:
            alert = (s.query(Alert)
                     .filter(Alert.fingerprint == fingerprint, Alert.status != 'resolved')
                     .order_by(Alert.id.desc()).first())
            now = _now()
            if alert:
                is_new = False
                if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(alert.severity, 0):
                    escalated = True
                    alert.severity = severity
                alert.last_seen = now
                alert.occurrences = (alert.occurrences or 1) + 1
                alert.title = title[:200]
                alert.message = (message or '')[:1000]
                if details is not None:
                    alert.details = details
            else:
                is_new = True
                alert = Alert(rule=rule, fingerprint=fingerprint, severity=severity, status='open',
                              title=title[:200], message=(message or '')[:1000], details=details,
                              first_seen=now, last_seen=now, occurrences=1)
                s.add(alert)
            s.commit()
            data = alert.to_dict()
            cooldown = current_app.config.get('ALERT_COOLDOWN_SECONDS', 900)
            due = (not alert.notified_at) or (now - alert.notified_at).total_seconds() >= cooldown
            should_notify = notify and severity != 'info' and (is_new or escalated or due)
            if should_notify:
                alert.notified_at = now
                s.commit()

        if is_new:
            logger.warning('ALERT raised [%s] %s: %s', severity, title, message,
                           extra={'fields': {'alert_rule': rule, 'fingerprint': fingerprint}})
            record_event('WARNING' if severity != 'critical' else 'ERROR', 'alert', f'alert_{rule}',
                         f'{title}: {message}', details=details)
        if should_notify:
            dispatch_notifications(data, is_new=is_new, escalated=escalated)
        elif notify and severity == 'info' and is_new:
            _push_to_admins(data)
        return data, is_new
    except Exception as exc:
        logger.error('Could not raise alert %s: %s', rule, exc)
        return None, False


def resolve_alert(fingerprint, by='auto'):
    try:
        with suppress_telemetry(), independent_session() as s:
            rows = s.query(Alert).filter(Alert.fingerprint == fingerprint, Alert.status != 'resolved').all()
            for a in rows:
                a.status = 'resolved'
                a.resolved_at = _now()
                a.resolved_by = by
            s.commit()
            if rows:
                logger.info('Alert resolved (%s): %s', by, rows[0].title)
            return len(rows)
    except Exception as exc:
        logger.error('Could not resolve alert %s: %s', fingerprint, exc)
        return 0


def acknowledge_alert(alert_id, user):
    with independent_session() as s:
        a = s.get(Alert, alert_id)
        if not a:
            return None
        if a.status == 'open':
            a.status = 'acknowledged'
            a.acknowledged_at = _now()
            a.acknowledged_by = user.id
            a.acknowledged_by_name = user.username
            s.commit()
        return a.to_dict()


def resolve_alert_by_id(alert_id, user):
    with independent_session() as s:
        a = s.get(Alert, alert_id)
        if not a:
            return None
        if a.status != 'resolved':
            a.status = 'resolved'
            a.resolved_at = _now()
            a.resolved_by = user.username
            s.commit()
        return a.to_dict()


def open_alerts(rule=None):
    with suppress_telemetry(), independent_session() as s:
        q = s.query(Alert).filter(Alert.status != 'resolved')
        if rule:
            q = q.filter(Alert.rule == rule)
        return [a.to_dict() for a in q.all()]


def summary():
    with suppress_telemetry(), independent_session() as s:
        rows = s.query(Alert.severity, Alert.status, db.func.count(Alert.id)) \
            .filter(Alert.status != 'resolved').group_by(Alert.severity, Alert.status).all()
    out = {'open': 0, 'acknowledged': 0, 'critical': 0, 'warning': 0, 'info': 0, 'total_active': 0}
    for sev, status, n in rows:
        out[status] = out.get(status, 0) + n
        out[sev] = out.get(sev, 0) + n
        out['total_active'] += n
    return out


# ------------------------------------------------------------ notifications
def _admin_ids():
    from models.user import User
    with suppress_telemetry(), independent_session() as s:
        return [r[0] for r in s.query(User.id).filter(User.is_admin == True, User.is_active == True).all()]  # noqa: E712


def _push_to_admins(data):
    try:
        for uid in _admin_ids():
            socketio.emit('admin_alert', data, room=f'user_{uid}')
    except Exception as exc:
        logger.debug('Socket push of alert failed: %s', exc)


def _text(data, is_new, escalated):
    tag = 'NEW' if is_new else ('ESCALATED' if escalated else 'ONGOING')
    return (f"[{data['severity'].upper()}] {tag}: {data['title']}\n{data['message'] or ''}\n"
            f"Rule: {data['rule']} | occurrences: {data['occurrences']} | first seen: {data['first_seen']}")


def dispatch_notifications(data, is_new=True, escalated=False):
    app = current_app._get_current_object()
    _push_to_admins(data)

    def work():
        with app.app_context():
            text = _text(data, is_new, escalated)
            url = app.config.get('ALERT_WEBHOOK_URL')
            if url:
                try:
                    import requests
                    requests.post(url, json={'text': text, 'content': text}, timeout=5)
                except Exception as exc:
                    logger.warning('Alert webhook failed: %s', exc)
            emails = app.config.get('ALERT_EMAILS') or []
            min_sev = app.config.get('ALERT_EMAIL_MIN_SEVERITY', 'critical')
            if (emails and app.config.get('MAIL_USERNAME')
                    and SEVERITY_RANK.get(data['severity'], 0) >= SEVERITY_RANK.get(min_sev, 2)):
                try:
                    from flask_mail import Message
                    from extensions import mail
                    mail.send(Message(subject=f"[{data['severity'].upper()}] {data['title']}",
                                      recipients=emails, body=text))
                except Exception as exc:
                    logger.warning('Alert e-mail failed: %s', exc)

    threading.Thread(target=work, daemon=True).start()


def send_test_alert(user):
    """Exercise every configured channel without creating a real incident."""
    now = _now()
    data = {
        'id': 0, 'rule': 'test', 'fingerprint': 'test', 'severity': 'warning',
        'status': 'open', 'title': 'Test alert',
        'message': f'Sent by {user.username} to verify alert delivery.',
        'details': None, 'occurrences': 1, 'first_seen': now.isoformat() + 'Z',
        'last_seen': now.isoformat() + 'Z', 'notified_at': None, 'acknowledged_at': None,
        'acknowledged_by': None, 'resolved_at': None, 'resolved_by': None,
    }
    dispatch_notifications(data, is_new=True)
    cfg = current_app.config
    return {
        'dashboard': True,
        'webhook': bool(cfg.get('ALERT_WEBHOOK_URL')),
        'email': bool(cfg.get('ALERT_EMAILS') and cfg.get('MAIL_USERNAME')),
    }
