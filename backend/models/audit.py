# backend/models/audit.py
from datetime import datetime, timedelta
from extensions import db
from sqlalchemy import Enum, Index, JSON, func, or_
import logging

from flask import g, has_request_context

from utils.redact import redact, parse_json_details
from utils.useragent import parse_user_agent, describe_user_agent
from utils.request_info import client_ip, current_request_id, current_user_agent

_log = logging.getLogger(__name__)


def iso_utc(dt):
    """ISO-8601 with an explicit UTC marker so every client parses it correctly."""
    return dt.isoformat() + 'Z' if dt else None


def user_summary(user, snapshot_username=None, snapshot_email=None, user_id=None):
    """
    Describe the person behind an audit/login row.

    Prefers the live user record. If the user has since been deleted the
    row's own snapshot (captured when the event happened) is used so the
    history never degrades into an anonymous "User #12".
    """
    if user is not None:
        return {
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'email': user.email,
            'is_admin': bool(user.is_admin),
            'is_active': bool(user.is_active),
            'is_suspended': bool(user.is_suspended),
            'deleted': False,
        }
    if user_id is not None or snapshot_username or snapshot_email:
        return {
            'id': user_id,
            'username': snapshot_username,
            'full_name': None,
            'email': snapshot_email,
            'is_admin': None,
            'is_active': None,
            'is_suspended': None,
            'deleted': user_id is not None,
        }
    return None

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    access_token = db.Column(db.String(500), nullable=False)
    refresh_token = db.Column(db.String(500), nullable=False)
    device_info = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_user_sessions', 'user_id'),
        Index('idx_expires_at', 'expires_at'),
        Index('idx_is_active', 'is_active'),
        Index('idx_user_active', 'user_id', 'is_active'),
    )
    
    def revoke(self):
        """Revoke the session"""
        self.is_active = False
        db.session.commit()
    
    def is_expired(self):
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at
    
    def extend_session(self, hours=24):
        """Extend session expiration"""
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
        db.session.commit()
    
    @classmethod
    def cleanup_expired_sessions(cls):
        """Clean up expired sessions"""
        expired = cls.query.filter(
            cls.expires_at < datetime.utcnow(),
            cls.is_active == True
        ).all()
        for session in expired:
            session.is_active = False
        db.session.commit()
        return len(expired)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'device_info': self.device_info,
            'ip_address': self.ip_address,
            'is_active': self.is_active,
            'expires_at': self.expires_at.isoformat(),
            'created_at': self.created_at.isoformat()
        }


class LoginHistory(db.Model):
    """
    One row per login attempt, successful or not.

    ``user_id`` is NULL when the attempt did not match any account (e.g. a
    mistyped or guessed username); ``identifier`` always records what was
    actually typed so those attempts are still traceable. ``failure_code`` is
    a stable machine-readable reason and ``failure_reason`` the readable one.
    """
    __tablename__ = 'login_history'

    # Failure codes that count towards the temporary lockout. Lockout
    # rejections themselves and account-state rejections (suspended, etc.)
    # deliberately do not.
    LOCKOUT_CODES = ('invalid_password', 'user_not_found')

    FAILURE_LABELS = {
        'invalid_password': 'Incorrect password',
        'user_not_found': 'No account with that username or email',
        'account_locked': 'Temporarily locked after too many failed attempts',
        'account_deactivated': 'Account is deactivated',
        'account_suspended': 'Account is suspended',
        'email_not_verified': 'Email address not verified',
        'invalid_request': 'Malformed login request',
        'server_error': 'Unexpected server error during login',
    }

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    identifier = db.Column(db.String(255))
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    device_type = db.Column(db.String(50))
    location = db.Column(db.String(255))
    success = db.Column(db.Boolean, default=True)
    failure_code = db.Column(db.String(40))
    failure_reason = db.Column(db.String(255))
    request_id = db.Column(db.String(36))

    __table_args__ = (
        Index('idx_user_login', 'user_id'),
        Index('idx_login_time', 'login_time'),
        Index('idx_success', 'success'),
        Index('idx_user_time', 'user_id', 'login_time'),
        Index('idx_login_identifier', 'identifier'),
        Index('idx_login_ip', 'ip_address'),
    )

    def logout(self):
        """Record logout time"""
        self.logout_time = datetime.utcnow()
        db.session.commit()

    @classmethod
    def get_recent_attempts(cls, user_id, hours=24):
        """Get recent login attempts for a user"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return cls.query.filter(
            cls.user_id == user_id,
            cls.login_time >= cutoff
        ).order_by(cls.login_time.desc()).all()

    @classmethod
    def count_recent_failures(cls, identifier=None, user_id=None, minutes=15):
        """
        Failed password attempts for an account in the last ``minutes``,
        counting only those after the account's last successful login (a
        good login clears the slate). Matches on the account id and/or the
        identifier that was typed, so guessing a username that does not
        exist is rate-limited too.
        """
        conds = []
        if user_id:
            conds.append(cls.user_id == user_id)
        if identifier:
            conds.append(func.lower(cls.identifier) == identifier.strip().lower())
        if not conds:
            return 0

        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        last_ok = db.session.query(func.max(cls.login_time)).filter(
            cls.success == True, or_(*conds)  # noqa: E712
        ).scalar()
        since = max(cutoff, last_ok) if last_ok else cutoff

        return cls.query.filter(
            cls.success == False,  # noqa: E712
            cls.failure_code.in_(cls.LOCKOUT_CODES),
            cls.login_time >= since,
            or_(*conds),
        ).count()

    @classmethod
    def count_failed_attempts(cls, user_id, minutes=15):
        """Backward-compatible wrapper (accepts a user id or an identifier)."""
        if isinstance(user_id, str):
            return cls.count_recent_failures(identifier=user_id, minutes=minutes)
        return cls.count_recent_failures(user_id=user_id, minutes=minutes)

    def to_dict(self, include_user=True):
        info = parse_user_agent(self.user_agent)
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'identifier': self.identifier,
            'login_time': iso_utc(self.login_time),
            'logout_time': iso_utc(self.logout_time),
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'device': describe_user_agent(self.user_agent),
            'device_type': self.device_type or info['device'],
            'location': self.location,
            'success': bool(self.success),
            'failure_code': self.failure_code,
            'failure_reason': self.failure_reason
            or (self.FAILURE_LABELS.get(self.failure_code) if not self.success else None),
            'request_id': self.request_id,
        }
        if include_user:
            data['user'] = user_summary(
                self.user, snapshot_username=None, snapshot_email=None, user_id=self.user_id
            ) if self.user_id else None
        return data


class AuditLog(db.Model):
    """
    Who did what, when, from where.

    The acting user's username/email (and a label for the affected resource)
    are copied into the row when it is written, so the trail stays readable
    after an account is renamed or deleted, and so failed logins for
    non-existent accounts (no ``user_id``) still say who they were for.
    """
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    actor_username = db.Column(db.String(100))
    actor_email = db.Column(db.String(255))
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.Integer)
    resource_label = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    request_id = db.Column(db.String(36))
    details = db.Column(JSON)
    status = db.Column(Enum('success', 'failure'), default='success')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_user_audit', 'user_id'),
        Index('idx_action', 'action'),
        Index('idx_created_at', 'created_at'),
        Index('idx_status', 'status'),
        Index('idx_audit_logs_timestamp', 'created_at'),
        Index('idx_user_action', 'user_id', 'action'),
    )

    @classmethod
    def log_action(cls, user_id, action, resource_type=None, resource_id=None,
                   ip_address=None, user_agent=None, details=None, status='success',
                   actor_username=None, actor_email=None, resource_label=None):
        """
        Create an audit entry. Never raises: a failure to write the audit
        trail must not break the action being audited.
        """
        try:
            if user_id and not (actor_username and actor_email):
                from models.user import User
                u = db.session.get(User, user_id)
                if u:
                    actor_username = actor_username or u.username
                    actor_email = actor_email or u.email

            log = cls(
                user_id=user_id,
                actor_username=(actor_username or None) and actor_username[:100],
                actor_email=(actor_email or None) and actor_email[:255],
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_label=(resource_label or None) and resource_label[:255],
                ip_address=ip_address or client_ip(),
                user_agent=user_agent or current_user_agent(),
                request_id=current_request_id(),
                # Store a real JSON object (not a JSON string inside the JSON
                # column) and never persist secrets.
                details=redact(details) if details else None,
                status=status,
            )
            db.session.add(log)
            db.session.commit()
            if has_request_context():
                g.audit_logged = True   # the automatic API-activity audit will skip this request
            return log
        except Exception as exc:  # pragma: no cover - defensive
            db.session.rollback()
            _log.error('Could not write audit log "%s": %s', action, exc)
            return None

    @classmethod
    def get_user_audit_trail(cls, user_id, limit=100):
        """Get audit trail for a user"""
        return cls.query.filter_by(
            user_id=user_id
        ).order_by(
            cls.created_at.desc()
        ).limit(limit).all()

    def to_dict(self, include_user=True, target=None):
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'resource_label': self.resource_label,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'device': describe_user_agent(self.user_agent) if self.user_agent else None,
            'request_id': self.request_id,
            'details': parse_json_details(self.details),
            'status': self.status,
            'created_at': iso_utc(self.created_at),
        }
        if include_user:
            if self.user_id is not None or self.actor_username:
                # A real account. If it no longer exists (deleting a user
                # clears user_id but the snapshot taken at write time stays)
                # the row still says who it was, flagged as deleted.
                summary = user_summary(
                    self.user if self.user_id else None,
                    snapshot_username=self.actor_username,
                    snapshot_email=self.actor_email,
                    user_id=self.user_id,
                )
                if summary and self.user_id is None:
                    summary['deleted'] = True
                data['user'] = summary
            elif self.action in ('login_failed', 'register_failed') and (self.resource_label or self.actor_email):
                # Someone who is not (or not yet) a user: the name that was typed.
                data['user'] = {
                    'id': None, 'username': self.resource_label, 'full_name': None,
                    'email': self.actor_email, 'is_admin': None, 'is_active': None,
                    'is_suspended': None, 'deleted': False, 'unregistered': True,
                }
            else:
                data['user'] = None
        if target is not None:
            data['target'] = target
        return data


class ArchivedChat(db.Model):
    __tablename__ = 'archived_chats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    chat_id = db.Column(db.Integer, nullable=False)
    chat_type = db.Column(Enum('user', 'group'), nullable=False)
    archived_at = db.Column(db.DateTime, default=datetime.utcnow)
    unarchive_at = db.Column(db.DateTime)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'chat_id', 'chat_type', name='unique_archive'),
        Index('idx_user_archives', 'user_id'),
        Index('idx_chat_archive', 'chat_id', 'chat_type'),
    )
    
    def unarchive(self):
        """Unarchive the chat"""
        db.session.delete(self)
        db.session.commit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'chat_type': self.chat_type,
            'archived_at': self.archived_at.isoformat()
        }


class PinnedChat(db.Model):
    __tablename__ = 'pinned_chats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    chat_id = db.Column(db.Integer, nullable=False)
    chat_type = db.Column(Enum('user', 'group'), nullable=False)
    pinned_at = db.Column(db.DateTime, default=datetime.utcnow)
    order_index = db.Column(db.Integer, default=0)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'chat_id', 'chat_type', name='unique_pin'),
        Index('idx_user_pins', 'user_id'),
        Index('idx_order', 'order_index'),
        Index('idx_chat_pin', 'chat_id', 'chat_type'),
    )
    
    def unpin(self):
        """Unpin the chat"""
        db.session.delete(self)
        db.session.commit()
    
    def update_order(self, new_index):
        """Update pin order"""
        self.order_index = new_index
        db.session.commit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'chat_type': self.chat_type,
            'pinned_at': self.pinned_at.isoformat(),
            'order_index': self.order_index
        }


class UserDevice(db.Model):
    __tablename__ = 'user_devices'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    device_id = db.Column(db.String(255), nullable=False)
    device_name = db.Column(db.String(100))
    device_type = db.Column(db.String(50))
    device_public_key = db.Column(db.Text, nullable=False)
    device_encrypted_private_key = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'device_id', name='unique_device'),
        Index('idx_user_devices', 'user_id'),
        Index('idx_is_active', 'is_active'),
        Index('idx_device_id', 'device_id'),
    )
    
    def update_last_active(self):
        """Update last active timestamp"""
        self.last_active = datetime.utcnow()
        db.session.commit()
    
    def revoke(self):
        """Revoke the device"""
        self.is_active = False
        db.session.commit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'device_id': self.device_id,
            'device_name': self.device_name,
            'device_type': self.device_type,
            'is_active': self.is_active,
            'last_active': self.last_active.isoformat(),
            'created_at': self.created_at.isoformat()
        }