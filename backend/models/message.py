# backend/models/message.py
from datetime import datetime
from extensions import db
from sqlalchemy import Enum, Index, and_, or_

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    recipient_type = db.Column(Enum('user', 'group'), nullable=False)
    recipient_id = db.Column(db.Integer, nullable=False)
    encrypted_message = db.Column(db.Text, nullable=False)
    encrypted_aes_key = db.Column(db.Text, nullable=False)
    # The same AES content key, wrapped a second time for the sender's own
    # public key. For direct messages this lets the sender decrypt their
    # own sent history later (their private key can't unwrap a key that
    # was only ever encrypted for the recipient). For group messages this
    # stays null — group members each hold their own wrapped copy of the
    # group's key via GroupMember.encrypted_group_key instead.
    encrypted_aes_key_sender = db.Column(db.Text)
    nonce = db.Column(db.String(64), nullable=False)
    tag = db.Column(db.String(64), nullable=False)
    digital_signature = db.Column(db.Text, nullable=False)
    message_type = db.Column(Enum('text', 'image', 'file', 'voice', 'video', 'audio'), default='text')
    file_url = db.Column(db.String(500))
    file_name = db.Column(db.String(255))
    file_size = db.Column(db.BigInteger)
    mime_type = db.Column(db.String(100))
    encryption_iv = db.Column(db.String(64))
    reply_to_message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='SET NULL'))
    is_deleted = db.Column(db.Boolean, default=False)
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime)
    is_pinned = db.Column(db.Boolean, default=False)
    is_starred = db.Column(db.Boolean, default=False)
    is_forwarded = db.Column(db.Boolean, default=False)
    original_sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    replies = db.relationship(
        'Message', 
        backref=db.backref('reply_to', remote_side=[id]),
        lazy='dynamic'
    )
    statuses = db.relationship(
        'MessageStatus', 
        backref='message', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    reactions = db.relationship(
        'MessageReaction', 
        backref='message', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    attachments = db.relationship(
        'MessageAttachment', 
        backref='message', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    voice_note = db.relationship(
        'VoiceNote',
        backref='message',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_sender', 'sender_id'),
        Index('idx_recipient', 'recipient_id'),
        Index('idx_recipient_type', 'recipient_type'),
        Index('idx_created_at', 'created_at'),
        Index('idx_message_type', 'message_type'),
        Index('idx_is_deleted', 'is_deleted'),
        Index('idx_expires_at', 'expires_at'),
        Index('idx_messages_recipient_created', 'recipient_id', 'recipient_type', 'created_at'),
        Index('idx_sender_recipient', 'sender_id', 'recipient_id', 'recipient_type'),
    )
    
    def mark_as_read(self, user_id):
        """Mark message as read for a user"""
        status = self.get_status_for_user(user_id)
        if status:
            status.status = 'read'
            status.read_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    def mark_as_delivered(self, user_id):
        """Mark message as delivered for a user"""
        status = self.get_status_for_user(user_id)
        if status:
            status.status = 'delivered'
            status.delivered_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    def get_status_for_user(self, user_id):
        """Get message status for a specific user"""
        return MessageStatus.query.filter_by(
            message_id=self.id,
            user_id=user_id
        ).first()
    
    def get_reactions(self):
        """Get all reactions for this message"""
        return self.reactions.all()
    
    def get_reaction_summary(self):
        """Get summary of reactions grouped by emoji"""
        from sqlalchemy import func
        summary = db.session.query(
            MessageReaction.reaction,
            func.count(MessageReaction.user_id).label('count')
        ).filter(
            MessageReaction.message_id == self.id
        ).group_by(
            MessageReaction.reaction
        ).all()
        return {r[0]: r[1] for r in summary}
    
    def add_reaction(self, user_id, reaction):
        """Add a reaction to the message"""
        existing = MessageReaction.query.filter_by(
            message_id=self.id,
            user_id=user_id
        ).first()
        
        if existing:
            if existing.reaction == reaction:
                db.session.delete(existing)
                db.session.commit()
                return None
            else:
                existing.reaction = reaction
                db.session.commit()
                return existing
        else:
            new_reaction = MessageReaction(
                message_id=self.id,
                user_id=user_id,
                reaction=reaction
            )
            db.session.add(new_reaction)
            db.session.commit()
            return new_reaction
    
    def edit_message(self, new_encrypted_message, new_encrypted_aes_key, new_nonce, new_tag, new_signature):
        """Edit an existing message"""
        self.encrypted_message = new_encrypted_message
        self.encrypted_aes_key = new_encrypted_aes_key
        self.nonce = new_nonce
        self.tag = new_tag
        self.digital_signature = new_signature
        self.is_edited = True
        self.edited_at = datetime.utcnow()
        db.session.commit()
    
    def delete_message(self, user_id, delete_for_everyone=False):
        """Delete a message"""
        if delete_for_everyone:
            self.is_deleted = True
            db.session.commit()
        else:
            # Delete for specific user (soft delete)
            status = self.get_status_for_user(user_id)
            if status:
                status.status = 'deleted'
                db.session.commit()
    
    def set_expiration(self, seconds):
        """Set message expiration time"""
        self.expires_at = datetime.utcnow() + timedelta(seconds=seconds)
        db.session.commit()
    
    def is_expired(self):
        """Check if message has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @classmethod
    def get_conversation(cls, user1_id, user2_id, limit=50, offset=0):
        """Get conversation between two users"""
        return cls.query.filter(
            or_(
                and_(
                    cls.sender_id == user1_id,
                    cls.recipient_id == user2_id,
                    cls.recipient_type == 'user'
                ),
                and_(
                    cls.sender_id == user2_id,
                    cls.recipient_id == user1_id,
                    cls.recipient_type == 'user'
                )
            ),
            cls.is_deleted == False
        ).order_by(
            cls.created_at.desc()
        ).limit(limit).offset(offset).all()
    
    @classmethod
    def get_group_messages(cls, group_id, limit=50, offset=0):
        """Get messages from a group"""
        return cls.query.filter(
            cls.recipient_id == group_id,
            cls.recipient_type == 'group',
            cls.is_deleted == False
        ).order_by(
            cls.created_at.desc()
        ).limit(limit).offset(offset).all()
    
    def to_dict(self, include_encrypted=False):
        """Convert message to dictionary"""
        data = {
            'id': self.id,
            'sender_id': self.sender_id,
            'recipient_type': self.recipient_type,
            'recipient_id': self.recipient_id,
            'message_type': self.message_type,
            'file_url': self.file_url,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'reply_to_message_id': self.reply_to_message_id,
            'is_edited': self.is_edited,
            'is_deleted': self.is_deleted,
            'is_pinned': self.is_pinned,
            'is_starred': self.is_starred,
            'is_forwarded': self.is_forwarded,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'reactions': self.get_reaction_summary()
        }
        
        if include_encrypted:
            data.update({
                'encrypted_message': self.encrypted_message,
                'encrypted_aes_key': self.encrypted_aes_key,
                'nonce': self.nonce,
                'tag': self.tag,
                'digital_signature': self.digital_signature
            })
        
        return data
    
    def __repr__(self):
        return f'<Message {self.id} from {self.sender_id} to {self.recipient_type}:{self.recipient_id}>'


class MessageStatus(db.Model):
    __tablename__ = 'message_status'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(Enum('sent', 'delivered', 'read', 'deleted'), default='sent')
    delivered_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', name='unique_message_user'),
        Index('idx_message_user', 'message_id', 'user_id'),
        Index('idx_status', 'status'),
        Index('idx_read_at', 'read_at'),
        Index('idx_user_status', 'user_id', 'status'),
    )
    
    def update_status(self, new_status):
        """Update the status of the message"""
        self.status = new_status
        if new_status == 'delivered':
            self.delivered_at = datetime.utcnow()
        elif new_status == 'read':
            self.read_at = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self):
        return {
            'message_id': self.message_id,
            'user_id': self.user_id,
            'status': self.status,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'created_at': self.created_at.isoformat()
        }


class MessageReaction(db.Model):
    __tablename__ = 'message_reactions'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    reaction = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', name='unique_reaction'),
        Index('idx_message_reactions', 'message_id'),
        Index('idx_user_reactions', 'user_id'),
    )
    
    def to_dict(self):
        return {
            'message_id': self.message_id,
            'user_id': self.user_id,
            'reaction': self.reaction,
            'created_at': self.created_at.isoformat()
        }