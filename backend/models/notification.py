# backend/models/notification.py
from datetime import datetime
from extensions import db
from sqlalchemy import Enum, Index

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    notification_type = db.Column(
        Enum('friend_request', 'message', 'group_invite', 'system', 'file', 'voice'),
        nullable=False
    )
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    message = db.Column(db.Text)
    reference_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False)
    is_seen = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    __table_args__ = (
        Index('idx_user_notifications', 'user_id'),
        Index('idx_is_read', 'is_read'),
        Index('idx_created_at', 'created_at'),
        Index('idx_notifications_user_read', 'user_id', 'is_read', 'created_at'),
        Index('idx_user_type', 'user_id', 'notification_type'),
    )
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()
        db.session.commit()
    
    def mark_as_seen(self):
        """Mark notification as seen"""
        self.is_seen = True
        db.session.commit()
    
    @classmethod
    def create_notification(cls, user_id, notification_type, sender_id=None, message=None, reference_id=None):
        """Create a new notification"""
        notification = cls(
            user_id=user_id,
            notification_type=notification_type,
            sender_id=sender_id,
            message=message,
            reference_id=reference_id
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    
    @classmethod
    def get_unread_for_user(cls, user_id):
        """Get all unread notifications for a user"""
        return cls.query.filter_by(
            user_id=user_id,
            is_read=False
        ).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_recent_for_user(cls, user_id, limit=20):
        """Get recent notifications for a user"""
        return cls.query.filter_by(
            user_id=user_id
        ).order_by(
            cls.created_at.desc()
        ).limit(limit).all()
    
    @classmethod
    def mark_all_as_read(cls, user_id):
        """Mark all notifications as read for a user"""
        notifications = cls.query.filter_by(user_id=user_id, is_read=False).all()
        for notification in notifications:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
        db.session.commit()
        return len(notifications)
    
    def to_dict(self, include_sender=False):
        """Convert notification to dictionary"""
        data = {
            'id': self.id,
            'notification_type': self.notification_type,
            'sender_id': self.sender_id,
            'message': self.message,
            'reference_id': self.reference_id,
            'is_read': self.is_read,
            'is_seen': self.is_seen,
            'created_at': self.created_at.isoformat(),
            'read_at': self.read_at.isoformat() if self.read_at else None
        }
        
        if include_sender and self.sender_id:
            from .user import User
            sender = User.query.get(self.sender_id)
            if sender:
                data['sender'] = {
                    'id': sender.id,
                    'username': sender.username,
                    'full_name': sender.full_name,
                    'profile_picture': sender.profile_picture
                }
        
        return data