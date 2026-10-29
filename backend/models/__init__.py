# backend/models/__init__.py
"""
Models package for Secure Chat Application
All database models with their relationships and methods
"""

from .user import User
from .message import Message, MessageStatus, MessageReaction
from .call_log import CallLog, GroupCallLog
from .friend import Friend, FriendRequest, BlockedUser
from .group import Group, GroupMember
from .file import File, VoiceNote, MessageAttachment
from .notification import Notification
from .push_subscription import PushSubscription
from .status import StatusPost, StatusRecipientKey, StatusView
from .audit import (
    UserSession, 
    LoginHistory, 
    AuditLog, 
    ArchivedChat, 
    PinnedChat, 
    UserDevice
)
from .monitoring import SystemEvent, Alert

__all__ = [
    'User',
    'Message',
    'MessageStatus',
    'MessageReaction',
    'CallLog',
    'GroupCallLog',
    'Friend',
    'FriendRequest',
    'BlockedUser',
    'Group',
    'GroupMember',
    'File',
    'VoiceNote',
    'MessageAttachment',
    'Notification',
    'PushSubscription',
    'StatusPost',
    'StatusRecipientKey',
    'StatusView',
    'UserSession',
    'LoginHistory',
    'AuditLog',
    'ArchivedChat',
    'PinnedChat',
    'UserDevice',
    'SystemEvent',
    'Alert'
]

# Import relationships after all models are defined
def setup_relationships():
    """Setup all relationships between models"""
    # This is called after all models are imported
    from .user import User
    from .message import Message
    from .friend import Friend
    from .group import GroupMember
    from .notification import Notification
    
    # User relationships
    User.sent_messages = db.relationship(
        'Message', 
        foreign_keys='Message.sender_id', 
        backref='sender', 
        lazy='dynamic'
    )
    # ... other relationships already defined in the models