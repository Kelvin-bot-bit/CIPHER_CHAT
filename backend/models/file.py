# backend/models/file.py
from datetime import datetime
from extensions import db
from sqlalchemy import Index

class File(db.Model):
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_hash = db.Column(db.String(64), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    mime_type = db.Column(db.String(100))
    # The file's own random AES-256 key, RSA-wrapped for the uploader's
    # public key. Previously this held the raw key in plaintext — anyone
    # with DB access could decrypt any file regardless of password. Now
    # it's protected the same way message content is: only whoever holds
    # the matching private key (unlocked by their password) can recover it.
    encryption_key = db.Column(db.Text, nullable=False)
    # A second wrapped copy for whoever the file was shared with, so they
    # can decrypt it too — populated only when the upload is linked to a
    # message (see FileService.upload_file). For a direct-message
    # attachment this is the recipient's RSA-OAEP-wrapped copy of the same
    # key. For a group attachment, RSA-wrapping once per member isn't
    # practical, so this instead holds the key AES-GCM-wrapped with the
    # group's own shared key (the same one every member already has their
    # own copy of via GroupMember.encrypted_group_key) —
    # encryption_key_wrap_nonce holds the nonce that wrapping needs. Null
    # for a file that isn't attached to any message (a personal vault
    # upload only the uploader can ever decrypt, which is correct for
    # that case).
    encryption_key_recipient = db.Column(db.Text)
    encryption_key_wrap_nonce = db.Column(db.String(64))
    encryption_iv = db.Column(db.String(64), nullable=False)
    is_encrypted = db.Column(db.Boolean, default=True)
    download_count = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    message_attachments = db.relationship(
        'MessageAttachment',
        backref='file',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_file_hash', 'file_hash'),
        Index('idx_uploader', 'uploader_id'),
        Index('idx_created_at', 'created_at'),
        Index('idx_expires_at', 'expires_at'),
        Index('idx_uploader_hash', 'uploader_id', 'file_hash'),
    )
    
    def increment_download_count(self):
        """Increment download counter"""
        self.download_count += 1
        db.session.commit()
    
    def is_expired(self):
        """Check if file has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def get_download_url(self):
        """Generate download URL"""
        return f"/api/files/download/{self.id}"
    
    def to_dict(self):
        return {
            'id': self.id,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'download_count': self.download_count,
            'is_encrypted': self.is_encrypted,
            'created_at': self.created_at.isoformat(),
            'download_url': self.get_download_url()
        }


class VoiceNote(db.Model):
    __tablename__ = 'voice_notes'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # Duration in seconds
    file_size = db.Column(db.BigInteger, nullable=False)
    # Same scheme as File above: RSA-wrapped for the uploader always, plus
    # a second copy for the recipient (RSA-wrapped for a direct chat,
    # AES-GCM-wrapped with the group's shared key for a group chat).
    encryption_key = db.Column(db.Text, nullable=False)
    encryption_key_recipient = db.Column(db.Text)
    encryption_key_wrap_nonce = db.Column(db.String(64))
    encryption_iv = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_message_voice', 'message_id'),
        Index('idx_created_at_voice', 'created_at'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'duration': self.duration,
            'duration_formatted': self.get_duration_formatted(),
            'file_size': self.file_size,
            'created_at': self.created_at.isoformat()
        }
    
    def get_duration_formatted(self):
        """Format duration as MM:SS"""
        minutes = self.duration // 60
        seconds = self.duration % 60
        return f"{minutes:02d}:{seconds:02d}"


class MessageAttachment(db.Model):
    __tablename__ = 'message_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey('files.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('message_id', 'file_id', name='unique_attachment'),
        Index('idx_message_attachments', 'message_id'),
        Index('idx_file_attachments', 'file_id'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'file_id': self.file_id,
            'created_at': self.created_at.isoformat()
        }