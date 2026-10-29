# backend/models/push_subscription.py
from datetime import datetime
from extensions import db
from sqlalchemy import Index

class PushSubscription(db.Model):
    """
    A browser's Web Push subscription — the endpoint URL and keys the
    browser's push service gave us when the user granted notification
    permission. One row per browser/device (a user with the app open on
    their phone and laptop has two rows), so a push is fanned out to every
    row for that user. Endpoints expire or get revoked periodically; a
    404/410 response when sending is how PushService detects and removes
    a dead one (see services/push_service.py).
    """
    __tablename__ = 'push_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    endpoint = db.Column(db.String(500), nullable=False, unique=True)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key = db.Column(db.String(255), nullable=False)
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_push_user', 'user_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'endpoint': self.endpoint,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat(),
        }