# backend/models/status.py
from datetime import datetime
from extensions import db

DEFAULT_STATUS_LIFETIME_HOURS = 24


class StatusPost(db.Model):
    """
    A "story"-style status update, visible to the poster's friends for a
    limited time. Encrypted the same way group messages are: a random AES
    key is generated per post, the caption is encrypted with it, and every
    current friend (plus the poster themself) gets their own RSA-wrapped
    copy of that key — see StatusRecipientKey. There's no retroactive
    access: someone who becomes a friend after a status was posted never
    gets a key for it, matching how a "story" visible only to friends-at
    -the-time is generally expected to work, and avoiding the complexity
    of re-wrapping every active status whenever a new friendship forms.

    The optional media — a photo or a short video — is a separate,
    self-contained encryption path (not routed through the shared
    File/FileService machinery). Its AES key is wrapped once, under the
    status's own key, via CryptoService.wrap_key_with_raw_key, the same
    mechanism already used to let every group member unwrap a
    group-attached file through the group's shared key. Every viewer who
    can unwrap the status key can therefore also unwrap the media key,
    with no per-viewer wrapping needed.

    The media columns are still named ``image_*`` (they predate video
    support, and renaming them would force a data migration); they hold
    the media of either kind. ``message_type`` says which one it is.
    """
    __tablename__ = 'status_posts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    message_type = db.Column(db.String(20), default='text')  # 'text' | 'image' | 'video'
    encrypted_content = db.Column(db.Text)  # AES-GCM ciphertext of the caption (may be an encrypted empty string for an image-only post)
    nonce = db.Column(db.String(64))
    tag = db.Column(db.String(64))
    digital_signature = db.Column(db.Text)
    # Only meaningful for a text-only post (the composer hides the picker
    # once an image is attached) — plaintext, not sensitive, just a UI
    # preference for how the caption is displayed.
    background_color = db.Column(db.String(20), default='#151D22')

    image_path = db.Column(db.String(500))
    image_mime_type = db.Column(db.String(100))
    image_size = db.Column(db.BigInteger)
    image_iv = db.Column(db.String(64))  # the image content's own AES-GCM nonce
    image_wrapped_key = db.Column(db.Text)  # image's AES key, wrapped under this status's key
    image_wrap_nonce = db.Column(db.String(64))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    is_deleted = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.Index('idx_status_user', 'user_id'),
        db.Index('idx_status_expires', 'expires_at'),
    )

    @property
    def media_type(self):
        """'image', 'video', or None for a text-only post."""
        if not self.image_path:
            return None
        return 'video' if self.message_type == 'video' else 'image'

    def to_dict(self):
        kind = self.media_type
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message_type': self.message_type,
            # `has_image` keeps its old meaning (a photo) so older clients
            # never try to draw a video inside an <img>.
            'has_image': kind == 'image',
            'has_video': kind == 'video',
            'has_media': kind is not None,
            'media_type': kind,
            'media_mime_type': self.image_mime_type if kind else None,
            'media_size': self.image_size if kind else None,
            'background_color': self.background_color,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'expires_at': self.expires_at.isoformat() + 'Z' if self.expires_at else None,
        }


class StatusRecipientKey(db.Model):
    """
    One row per (status, person who can view it) — that person's own
    RSA-wrapped copy of the status's AES content key. Populated once, at
    post time, for the poster themself and every friend they had at that
    moment (see StatusService.create_status).
    """
    __tablename__ = 'status_recipient_keys'

    id = db.Column(db.Integer, primary_key=True)
    status_id = db.Column(db.Integer, db.ForeignKey('status_posts.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    encrypted_status_key = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('status_id', 'user_id', name='unique_status_recipient'),
        db.Index('idx_status_recipient_user', 'user_id'),
    )


class StatusView(db.Model):
    """Tracks who has viewed a status, for the poster's own 'seen by' list."""
    __tablename__ = 'status_views'

    id = db.Column(db.Integer, primary_key=True)
    status_id = db.Column(db.Integer, db.ForeignKey('status_posts.id', ondelete='CASCADE'), nullable=False)
    viewer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('status_id', 'viewer_id', name='unique_status_view'),
    )

    def to_dict(self):
        return {
            'viewer_id': self.viewer_id,
            'viewed_at': self.viewed_at.isoformat() + 'Z' if self.viewed_at else None,
        }