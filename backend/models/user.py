# backend/models/user.py
from datetime import datetime, timedelta
from extensions import db
from sqlalchemy import Enum, Index
from sqlalchemy.orm import validates
import re

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100))
    profile_picture = db.Column(db.String(500), default='default_avatar.png')
    bio = db.Column(db.Text)
    public_key = db.Column(db.Text, nullable=False)
    encrypted_private_key = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_suspended = db.Column(db.Boolean, default=False)
    online_status = db.Column(Enum('online', 'offline', 'away', 'busy'), default='offline')
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sent_messages = db.relationship(
        'Message', 
        foreign_keys='Message.sender_id', 
        backref='sender', 
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    received_messages = db.relationship(
        'Message',
        foreign_keys='Message.recipient_id',
        lazy='dynamic',
        primaryjoin='and_(Message.recipient_id == User.id, Message.recipient_type == "user")'
    )
    friend_requests_sent = db.relationship(
        'FriendRequest', 
        foreign_keys='FriendRequest.sender_id', 
        backref='sender', 
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    friend_requests_received = db.relationship(
        'FriendRequest', 
        foreign_keys='FriendRequest.receiver_id', 
        backref='receiver', 
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    friends_as_user = db.relationship(
        'Friend',
        foreign_keys='Friend.user_id',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    friends_as_friend = db.relationship(
        'Friend',
        foreign_keys='Friend.friend_id',
        backref='friend_user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    blocked_users = db.relationship(
        'BlockedUser',
        foreign_keys='BlockedUser.blocker_id',
        backref='blocker',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    blocked_by_users = db.relationship(
        'BlockedUser',
        foreign_keys='BlockedUser.blocked_id',
        backref='blocked',
        lazy='dynamic'
    )
    notifications = db.relationship(
        'Notification', 
        foreign_keys='Notification.user_id', 
        backref='user', 
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    sent_notifications = db.relationship(
        'Notification',
        foreign_keys='Notification.sender_id',
        backref='sender_user',
        lazy='dynamic'
    )
    group_memberships = db.relationship(
        'GroupMember', 
        backref='user', 
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    groups_created = db.relationship(
        'Group',
        foreign_keys='Group.created_by',
        backref='creator',
        lazy='dynamic'
    )
    user_sessions = db.relationship(
        'UserSession', 
        backref='user', 
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    # Login history is security evidence: when an account is deleted its
    # rows are kept (user_id set to NULL, the typed identifier is retained)
    # instead of being deleted along with the account.
    login_history = db.relationship(
        'LoginHistory',
        backref='user',
        lazy='dynamic',
        cascade='save-update, merge'
    )
    audit_logs = db.relationship(
        'AuditLog',
        backref='user',
        lazy='dynamic'
    )
    uploaded_files = db.relationship(
        'File',
        backref='uploader',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    devices = db.relationship(
        'UserDevice',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    archived_chats = db.relationship(
        'ArchivedChat',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    pinned_chats = db.relationship(
        'PinnedChat',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_username', 'username'),
        Index('idx_email', 'email'),
        Index('idx_online_status', 'online_status'),
        Index('idx_last_seen', 'last_seen'),
        Index('idx_username_email', 'username', 'email'),
    )
    
    @validates('username')
    def validate_username(self, key, username):
        """Validate username format"""
        if not username or len(username) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return username.lower()
    
    @validates('email')
    def validate_email(self, key, email):
        """Validate email format"""
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValueError('Invalid email address')
        return email.lower()
    
    @property
    def is_authenticated(self):
        """Check if user is authenticated"""
        return True
    
    @property
    def is_online(self):
        """Check if user is currently online"""
        return self.online_status == 'online'
    
    @property
    def last_online(self):
        """Get time since last online"""
        if self.last_seen:
            delta = datetime.utcnow() - self.last_seen
            if delta.seconds < 60:
                return f"{delta.seconds} seconds ago"
            elif delta.seconds < 3600:
                return f"{delta.seconds // 60} minutes ago"
            elif delta.seconds < 86400:
                return f"{delta.seconds // 3600} hours ago"
            else:
                return f"{delta.days} days ago"
        return "Never"
    
    @property
    def friend_count(self):
        """Get total number of friends"""
        return self.friends_as_user.filter_by(is_blocked=False).count()
    
    @property
    def pending_requests(self):
        """Get pending friend requests"""
        return self.friend_requests_received.filter_by(status='pending').count()
    
    def get_public_key(self):
        """Get user's public key"""
        return self.public_key
    
    def update_last_seen(self):
        """Update last seen timestamp"""
        self.last_seen = datetime.utcnow()
        db.session.commit()
    
    def update_online_status(self, status):
        """Update online status"""
        if status in ['online', 'offline', 'away', 'busy']:
            self.online_status = status
            if status == 'offline':
                self.last_seen = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    def get_friends(self):
        """Get list of friends"""
        from .friend import Friend
        friend_ids = Friend.query.filter_by(
            user_id=self.id,
            is_blocked=False
        ).with_entities(Friend.friend_id).all()
        return [f[0] for f in friend_ids]
    
    def get_friends_list(self):
        """Get full friend objects"""
        friend_ids = self.get_friends()
        return User.query.filter(User.id.in_(friend_ids)).all()
    
    def is_friend(self, user_id):
        """Check if a user is a friend"""
        from .friend import Friend
        return Friend.query.filter_by(
            user_id=self.id,
            friend_id=user_id,
            is_blocked=False
        ).first() is not None
    
    def is_blocked(self, user_id):
        """Check if a user is blocked"""
        from .friend import Friend
        return Friend.query.filter_by(
            user_id=self.id,
            friend_id=user_id,
            is_blocked=True
        ).first() is not None
    
    def get_unread_count(self):
        """Get total unread messages"""
        from .message import Message, MessageStatus
        unread = MessageStatus.query.join(
            Message, Message.id == MessageStatus.message_id
        ).filter(
            MessageStatus.user_id == self.id,
            MessageStatus.status != 'read',
            Message.is_deleted == False
        ).count()
        return unread
    
    def get_recent_conversations(self, limit=20):
        """Get recent conversations with their last messages"""
        from .message import Message, MessageStatus
        from .friend import Friend
        
        # Get recent conversations
        conversations = []
        
        # Direct messages
        direct_messages = db.session.query(
            Message,
            User.username,
            User.full_name,
            User.profile_picture,
            User.online_status,
            User.last_seen,
            MessageStatus.status.label('message_status')
        ).join(
            User, User.id == Message.sender_id
        ).outerjoin(
            MessageStatus, db.and_(
                MessageStatus.message_id == Message.id,
                MessageStatus.user_id == self.id
            )
        ).filter(
            db.or_(
                db.and_(
                    Message.sender_id == self.id,
                    Message.recipient_type == 'user'
                ),
                db.and_(
                    Message.recipient_id == self.id,
                    Message.recipient_type == 'user'
                )
            ),
            Message.is_deleted == False
        ).order_by(
            Message.created_at.desc()
        ).limit(limit).all()
        
        for msg, username, full_name, profile_pic, online_status, last_seen, msg_status in direct_messages:
            other_user_id = msg.recipient_id if msg.sender_id == self.id else msg.sender_id
            conversations.append({
                'type': 'user',
                'user_id': other_user_id,
                'username': username,
                'full_name': full_name,
                'profile_picture': profile_pic,
                'online_status': online_status,
                'last_seen': last_seen,
                'last_message': msg.encrypted_message,
                'last_message_time': msg.created_at,
                'message_status': msg_status,
                'message_id': msg.id
            })
        
        return conversations
    
    def to_dict(self, include_private=False, include_keys=False):
        """Convert user to dictionary"""
        data = {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'profile_picture': self.profile_picture,
            'bio': self.bio,
            'online_status': self.online_status,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'last_online': self.last_online,
            'is_verified': self.is_verified,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'is_suspended': self.is_suspended,
            'friend_count': self.friend_count,
            'unread_count': self.get_unread_count(),
            'created_at': self.created_at.isoformat()
        }
        
        if include_private:
            data.update({
                'email': self.email,
                'is_authenticated': self.is_authenticated
            })
        
        if include_keys:
            data.update({
                'public_key': self.public_key
            })
        
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'