# backend/models/friend.py
from datetime import datetime
from extensions import db
from sqlalchemy import Enum, Index, and_, or_

class Friend(db.Model):
    __tablename__ = 'friends'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    blocked_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    nickname = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'friend_id', name='unique_friendship'),
        Index('idx_user_friend', 'user_id', 'friend_id'),
        Index('idx_is_blocked', 'is_blocked'),
        Index('idx_user_blocked', 'user_id', 'is_blocked'),
    )
    
    def block(self, blocker_id):
        """Block a friend"""
        self.is_blocked = True
        self.blocked_by = blocker_id
        db.session.commit()
    
    def unblock(self):
        """Unblock a friend"""
        self.is_blocked = False
        self.blocked_by = None
        db.session.commit()
    
    def set_nickname(self, nickname):
        """Set a nickname for the friend"""
        self.nickname = nickname
        db.session.commit()
    
    @classmethod
    def get_friend_ids(cls, user_id, include_blocked=False):
        """Get all friend IDs for a user"""
        query = cls.query.filter_by(user_id=user_id)
        if not include_blocked:
            query = query.filter_by(is_blocked=False)
        return [f.friend_id for f in query.all()]
    
    @classmethod
    def are_friends(cls, user1_id, user2_id):
        """Check if two users are friends"""
        return cls.query.filter(
            or_(
                and_(cls.user_id == user1_id, cls.friend_id == user2_id),
                and_(cls.user_id == user2_id, cls.friend_id == user1_id)
            ),
            cls.is_blocked == False
        ).first() is not None
    
    @classmethod
    def is_blocked_relationship(cls, user_id, other_id):
        """Check if a user has blocked another"""
        return cls.query.filter(
            cls.user_id == user_id,
            cls.friend_id == other_id,
            cls.is_blocked == True
        ).first() is not None
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'friend_id': self.friend_id,
            'is_blocked': self.is_blocked,
            'blocked_by': self.blocked_by,
            'nickname': self.nickname,
            'created_at': self.created_at.isoformat()
        }


class FriendRequest(db.Model):
    __tablename__ = 'friend_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(Enum('pending', 'accepted', 'rejected', 'cancelled'), default='pending')
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('sender_id', 'receiver_id', name='unique_request'),
        Index('idx_sender_receiver', 'sender_id', 'receiver_id'),
        Index('idx_status', 'status'),
        Index('idx_created_at', 'created_at'),
        Index('idx_receiver_status', 'receiver_id', 'status'),
    )
    
    def accept(self):
        """Accept friend request"""
        if self.status != 'pending':
            raise ValueError('Request is not pending')
        
        self.status = 'accepted'
        
        # Create friendship entries
        friendship1 = Friend(user_id=self.sender_id, friend_id=self.receiver_id)
        friendship2 = Friend(user_id=self.receiver_id, friend_id=self.sender_id)
        
        db.session.add(friendship1)
        db.session.add(friendship2)
        db.session.commit()
        
        # Create notifications
        from .notification import Notification
        notification = Notification(
            user_id=self.sender_id,
            notification_type='friend_request',
            sender_id=self.receiver_id,
            message=f'{self.receiver_id} accepted your friend request',
            reference_id=self.id
        )
        db.session.add(notification)
        db.session.commit()
    
    def reject(self):
        """Reject friend request"""
        if self.status != 'pending':
            raise ValueError('Request is not pending')
        self.status = 'rejected'
        db.session.commit()
    
    def cancel(self):
        """Cancel friend request"""
        if self.status != 'pending':
            raise ValueError('Request is not pending')
        self.status = 'cancelled'
        db.session.commit()
    
    @classmethod
    def get_pending_for_user(cls, user_id):
        """Get all pending friend requests for a user"""
        return cls.query.filter_by(
            receiver_id=user_id,
            status='pending'
        ).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_sent_requests(cls, user_id):
        """Get all friend requests sent by a user"""
        return cls.query.filter_by(
            sender_id=user_id
        ).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def has_pending_request(cls, sender_id, receiver_id):
        """Check if there's a pending request between two users"""
        return cls.query.filter(
            or_(
                and_(cls.sender_id == sender_id, cls.receiver_id == receiver_id),
                and_(cls.sender_id == receiver_id, cls.receiver_id == sender_id)
            ),
            cls.status == 'pending'
        ).first() is not None
    
    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'status': self.status,
            'message': self.message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class BlockedUser(db.Model):
    __tablename__ = 'blocked_users'
    
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('blocker_id', 'blocked_id', name='unique_block'),
        Index('idx_blocker_blocked', 'blocker_id', 'blocked_id'),
        Index('idx_blocker', 'blocker_id'),
        Index('idx_blocked', 'blocked_id'),
    )
    
    def unblock(self):
        """Unblock the user"""
        db.session.delete(self)
        db.session.commit()
    
    @classmethod
    def is_blocked(cls, blocker_id, blocked_id):
        """Check if a user has blocked another"""
        return cls.query.filter_by(
            blocker_id=blocker_id,
            blocked_id=blocked_id
        ).first() is not None
    
    @classmethod
    def get_blocked_users(cls, user_id):
        """Get all users blocked by a user"""
        return [b.blocked_id for b in cls.query.filter_by(blocker_id=user_id).all()]
    
    def to_dict(self):
        return {
            'id': self.id,
            'blocker_id': self.blocker_id,
            'blocked_id': self.blocked_id,
            'reason': self.reason,
            'created_at': self.created_at.isoformat()
        }