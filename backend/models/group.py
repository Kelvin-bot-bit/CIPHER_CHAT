# backend/models/group.py
from datetime import datetime
from extensions import db
from sqlalchemy import Enum, Index, and_

class Group(db.Model):
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(100), nullable=False)
    group_description = db.Column(db.Text)
    group_picture = db.Column(db.String(500), default='default_group.png')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_private = db.Column(db.Boolean, default=False)
    group_key = db.Column(db.Text)  # Encrypted group key for E2EE
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    members = db.relationship(
        'GroupMember', 
        backref='group', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_group_name', 'group_name'),
        Index('idx_is_active', 'is_active'),
        Index('idx_created_by', 'created_by'),
        Index('idx_group_name_active', 'group_name', 'is_active'),
    )
    
    def add_member(self, user_id, role='member', encrypted_group_key=None):
        """Add a member to the group"""
        if self.is_member(user_id):
            raise ValueError('User is already a member of this group')
        
        member = GroupMember(
            group_id=self.id,
            user_id=user_id,
            role=role,
            encrypted_group_key=encrypted_group_key
        )
        db.session.add(member)
        db.session.commit()
        
        # Create notification
        from .notification import Notification
        notification = Notification(
            user_id=user_id,
            notification_type='group_invite',
            sender_id=self.created_by,
            message=f'You have been added to group "{self.group_name}"',
            reference_id=self.id
        )
        db.session.add(notification)
        db.session.commit()
        
        return member
    
    def remove_member(self, user_id, removed_by=None):
        """Remove a member from the group"""
        member = GroupMember.query.filter_by(
            group_id=self.id,
            user_id=user_id,
            is_active=True
        ).first()
        
        if not member:
            raise ValueError('User is not a member of this group')
        
        member.is_active = False
        db.session.commit()
        
        # Create notification
        if removed_by:
            from .notification import Notification
            notification = Notification(
                user_id=user_id,
                notification_type='system',
                sender_id=removed_by,
                message=f'You have been removed from group "{self.group_name}"',
                reference_id=self.id
            )
            db.session.add(notification)
            db.session.commit()
    
    def is_member(self, user_id):
        """Check if a user is a member of the group"""
        return GroupMember.query.filter_by(
            group_id=self.id,
            user_id=user_id,
            is_active=True
        ).first() is not None
    
    def is_admin(self, user_id):
        """Check if a user is an admin of the group"""
        member = GroupMember.query.filter_by(
            group_id=self.id,
            user_id=user_id,
            is_active=True
        ).first()
        return member and member.role == 'admin'
    
    def promote_to_admin(self, user_id):
        """Promote a member to admin"""
        member = GroupMember.query.filter_by(
            group_id=self.id,
            user_id=user_id,
            is_active=True
        ).first()
        if member:
            member.role = 'admin'
            db.session.commit()
            return True
        return False
    
    def demote_from_admin(self, user_id):
        """Demote an admin to member"""
        member = GroupMember.query.filter_by(
            group_id=self.id,
            user_id=user_id,
            is_active=True
        ).first()
        if member and member.role == 'admin':
            member.role = 'member'
            db.session.commit()
            return True
        return False
    
    def get_member_count(self):
        """Get the number of active members"""
        return GroupMember.query.filter_by(
            group_id=self.id,
            is_active=True
        ).count()
    
    def get_active_members(self):
        """Get all active members"""
        return GroupMember.query.filter_by(
            group_id=self.id,
            is_active=True
        ).all()
    
    def get_member_ids(self):
        """Get all active member IDs"""
        return [m.user_id for m in self.get_active_members()]
    
    def update_group_key(self, new_key):
        """Update the group encryption key"""
        self.group_key = new_key
        db.session.commit()
    
    def delete_group(self):
        """Soft delete the group"""
        self.is_active = False
        db.session.commit()
    
    def to_dict(self, include_members=False):
        """Convert group to dictionary"""
        data = {
            'id': self.id,
            'group_name': self.group_name,
            'group_description': self.group_description,
            'group_picture': self.group_picture,
            'created_by': self.created_by,
            'is_private': self.is_private,
            'is_active': self.is_active,
            'member_count': self.get_member_count(),
            'created_at': self.created_at.isoformat()
        }
        
        if include_members:
            data['members'] = [
                {
                    'user_id': m.user_id,
                    'role': m.role,
                    'joined_at': m.joined_at.isoformat()
                }
                for m in self.get_active_members()
            ]
        
        return data


class GroupMember(db.Model):
    __tablename__ = 'group_members'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(Enum('admin', 'member', 'moderator'), default='member')
    is_active = db.Column(db.Boolean, default=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_read_message_id = db.Column(db.Integer)
    # This member's own RSA-wrapped copy of the group's raw AES content key
    # (base64). Every member needs their own copy, wrapped with their own
    # public key, so they can unwrap it with their own private key — a
    # single shared copy (as the old `Group.group_key` column held, wrapped
    # only for the creator) means nobody else can ever decrypt anything.
    # See GroupService.create_group / add_member_to_group for how this gets
    # populated, and CryptoService.decrypt_group_key for how it's unwrapped.
    encrypted_group_key = db.Column(db.Text)
    
    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='unique_group_member'),
        Index('idx_group_members', 'group_id', 'user_id'),
        Index('idx_role', 'role'),
        Index('idx_is_active', 'is_active'),
        Index('idx_group_active', 'group_id', 'is_active'),
    )
    
    def update_last_read(self, message_id):
        """Update the last read message ID"""
        self.last_read_message_id = message_id
        db.session.commit()
    
    def get_unread_count(self):
        """Get unread messages for this member"""
        from .message import Message, MessageStatus
        if self.last_read_message_id:
            return Message.query.filter(
                Message.recipient_id == self.group_id,
                Message.recipient_type == 'group',
                Message.id > self.last_read_message_id,
                Message.is_deleted == False
            ).count()
        else:
            return Message.query.filter(
                Message.recipient_id == self.group_id,
                Message.recipient_type == 'group',
                Message.is_deleted == False
            ).count()
    
    def to_dict(self):
        return {
            'group_id': self.group_id,
            'user_id': self.user_id,
            'role': self.role,
            'is_active': self.is_active,
            'joined_at': self.joined_at.isoformat(),
            'last_read_message_id': self.last_read_message_id
        }