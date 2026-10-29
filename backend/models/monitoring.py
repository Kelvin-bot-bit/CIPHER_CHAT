# backend/models/monitoring.py
"""
Persistent observability records.

* ``SystemEvent``  - notable things the *system* did or experienced: server
  errors, slow requests, health-check state changes, security signals.
  (What *users* did lives in ``AuditLog``.)
* ``Alert``        - de-duplicated, stateful notifications raised by the alert
  rules (open -> acknowledged -> resolved).

The high-volume per-request data (every request, every log line) is kept in
bounded in-memory ring buffers and in rotating log files instead, so the
database only stores what is worth keeping.
"""
from datetime import datetime
from sqlalchemy import Index, JSON
from extensions import db
from models.audit import iso_utc
from utils.redact import parse_json_details

LEVELS = ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
SEVERITIES = ('info', 'warning', 'critical')
SEVERITY_RANK = {'info': 0, 'warning': 1, 'critical': 2}


class SystemEvent(db.Model):
    __tablename__ = 'system_events'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    level = db.Column(db.String(10), nullable=False, default='INFO')
    category = db.Column(db.String(30), nullable=False)      # request | database | auth | security | system | alert | admin
    event = db.Column(db.String(80), nullable=False)         # stable code, e.g. server_error, slow_request
    message = db.Column(db.String(500))
    request_id = db.Column(db.String(36))
    user_id = db.Column(db.Integer)                          # no FK on purpose: survives user deletion
    username = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    method = db.Column(db.String(10))
    path = db.Column(db.String(255))
    status_code = db.Column(db.Integer)
    duration_ms = db.Column(db.Float)
    details = db.Column(JSON)

    __table_args__ = (
        Index('idx_sysevent_created', 'created_at'),
        Index('idx_sysevent_level', 'level'),
        Index('idx_sysevent_category', 'category'),
        Index('idx_sysevent_event', 'event'),
        Index('idx_sysevent_request', 'request_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': iso_utc(self.created_at),
            'level': self.level,
            'category': self.category,
            'event': self.event,
            'message': self.message,
            'request_id': self.request_id,
            'user_id': self.user_id,
            'username': self.username,
            'ip_address': self.ip_address,
            'method': self.method,
            'path': self.path,
            'status_code': self.status_code,
            'duration_ms': round(self.duration_ms, 1) if self.duration_ms is not None else None,
            'details': parse_json_details(self.details),
        }


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    rule = db.Column(db.String(60), nullable=False)
    fingerprint = db.Column(db.String(160), nullable=False)       # dedupe key: rule + subject
    severity = db.Column(db.String(10), nullable=False, default='warning')
    status = db.Column(db.String(15), nullable=False, default='open')  # open | acknowledged | resolved
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(1000))
    details = db.Column(JSON)
    occurrences = db.Column(db.Integer, default=1)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notified_at = db.Column(db.DateTime)
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.Integer)
    acknowledged_by_name = db.Column(db.String(100))
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.String(100))                       # username, or "auto"

    __table_args__ = (
        Index('idx_alert_status', 'status'),
        Index('idx_alert_fingerprint', 'fingerprint'),
        Index('idx_alert_last_seen', 'last_seen'),
        Index('idx_alert_severity', 'severity'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'rule': self.rule,
            'fingerprint': self.fingerprint,
            'severity': self.severity,
            'status': self.status,
            'title': self.title,
            'message': self.message,
            'details': parse_json_details(self.details),
            'occurrences': self.occurrences or 1,
            'first_seen': iso_utc(self.first_seen),
            'last_seen': iso_utc(self.last_seen),
            'notified_at': iso_utc(self.notified_at),
            'acknowledged_at': iso_utc(self.acknowledged_at),
            'acknowledged_by': self.acknowledged_by_name,
            'resolved_at': iso_utc(self.resolved_at),
            'resolved_by': self.resolved_by,
        }
