# backend/services/voice_service.py
import os
import uuid
import base64
import logging
from flask import current_app
from extensions import db
from models import VoiceNote, Message, User
from services.crypto_service import CryptoService

logger = logging.getLogger(__name__)


class VoiceService:
    """Handles voice note upload, storage, and retrieval.

    Encryption follows the same pattern as FileService: a random AES-256-GCM
    key generated per recording, RSA-wrapped for the uploader and for
    whoever the recording was sent to (RSA-wrapped for a direct recipient,
    or AES-GCM-wrapped with the group's shared key for a group recipient —
    see the comment on File.encryption_key_recipient in models/file.py for
    why groups use a different mechanism). The key is no longer stored in
    plaintext.
    """

    MAX_VOICE_SIZE = 15 * 1024 * 1024  # 15MB — generous for a voice note
    ALLOWED_EXTENSIONS = {'webm', 'ogg', 'mp3', 'wav', 'm4a', 'aac'}

    @staticmethod
    def allowed_file(filename: str) -> bool:
        if '.' not in filename:
            return False
        return filename.rsplit('.', 1)[1].lower() in VoiceService.ALLOWED_EXTENSIONS

    @staticmethod
    def _check_message_access(message: Message, user_id: int) -> bool:
        if message.recipient_type == 'user':
            return message.sender_id == user_id or message.recipient_id == user_id
        elif message.recipient_type == 'group':
            from .group_service import GroupService
            return GroupService.is_member(user_id, message.recipient_id)
        return False

    @staticmethod
    def upload_voice_note(
        file_data: bytes,
        filename: str,
        message_id: int,
        duration: int,
        uploader_id: int,
        uploader_password: str = None
    ) -> dict:
        """
        Encrypt and store a voice recording, attached to an existing message.

        Args:
            file_data: Raw audio bytes
            filename: Original filename (used only to check the extension)
            message_id: The message this recording belongs to
            duration: Recording length in whole seconds
            uploader_id: ID of the user uploading
            uploader_password: Required only when the message's recipient
                is a group — needed to unwrap the uploader's own copy of
                that group's key so the recording's key can be wrapped
                with it too. Not needed for a direct message, since
                wrapping the recipient's copy there only needs their
                public key.

        Returns:
            Dictionary with the voice note data or an error
        """
        if len(file_data) > VoiceService.MAX_VOICE_SIZE:
            return {'error': f'Voice note exceeds maximum of {VoiceService.MAX_VOICE_SIZE // 1024 // 1024}MB'}

        if not VoiceService.allowed_file(filename):
            return {'error': 'Unsupported audio format'}

        message = Message.query.get(message_id)
        if not message:
            return {'error': 'Message not found'}
        if message.sender_id != uploader_id:
            return {'error': 'You can only attach a voice note to your own message'}

        uploader = User.query.get(uploader_id)
        if not uploader:
            return {'error': 'Uploader not found'}

        recipient_user = None
        group_member = None
        if message.recipient_type == 'user':
            recipient_user = User.query.get(message.recipient_id)
        else:
            from models import Group, GroupMember
            group_member = GroupMember.query.filter_by(
                group_id=message.recipient_id, user_id=uploader_id, is_active=True
            ).first()
            if not group_member or not group_member.encrypted_group_key:
                return {'error': 'Your group key is missing — try leaving and rejoining the group'}
            if not uploader_password:
                return {'error': 'Password required to send a voice note in a group (needed to unwrap the group key)'}

        try:
            encrypted = CryptoService.encrypt_file(file_data)
            raw_aes_key = base64.b64decode(encrypted['encryption_key'])

            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'voice')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, f"{uuid.uuid4()}.enc")

            with open(file_path, 'wb') as f:
                f.write(encrypted['encrypted_data'])

            wrapped_for_uploader = CryptoService.encrypt_group_key(raw_aes_key, uploader.public_key)

            wrapped_for_recipient = None
            wrap_nonce = None
            if recipient_user:
                wrapped_for_recipient = CryptoService.encrypt_group_key(raw_aes_key, recipient_user.public_key)
            elif group_member:
                raw_group_key = CryptoService.decrypt_group_key(
                    group_member.encrypted_group_key,
                    CryptoService.decrypt_private_key_with_password(uploader.encrypted_private_key, uploader_password)
                )
                wrap_result = CryptoService.wrap_key_with_raw_key(raw_aes_key, raw_group_key)
                wrapped_for_recipient = wrap_result['wrapped_key']
                wrap_nonce = wrap_result['wrap_nonce']

            voice_note = VoiceNote(
                message_id=message_id,
                file_path=file_path,
                duration=duration,
                file_size=len(file_data),
                encryption_key=wrapped_for_uploader,
                encryption_key_recipient=wrapped_for_recipient,
                encryption_key_wrap_nonce=wrap_nonce,
                encryption_iv=encrypted['nonce']
            )
            db.session.add(voice_note)
            db.session.commit()

            return {'success': True, 'voice_note': voice_note.to_dict()}

        except Exception as e:
            db.session.rollback()
            logger.error(f"Upload voice note error: {str(e)}")
            return {'error': f'Failed to upload voice note: {str(e)}'}

    @staticmethod
    def download_voice_note(voice_note_id: int, user_id: int, password: str) -> dict:
        """
        Decrypt and return a voice note's audio data.

        Args:
            voice_note_id: Voice note ID
            user_id: Current user ID
            password: Requester's password — needed to unlock their
                private key (or their group key) to unwrap the
                recording's AES key. Previously unused since the key was
                stored in plaintext; now load-bearing.

        Returns:
            Dictionary with decrypted audio bytes or an error
        """
        voice_note = VoiceNote.query.get(voice_note_id)
        if not voice_note:
            return {'error': 'Voice note not found'}

        message = Message.query.get(voice_note.message_id)
        if not message or not VoiceService._check_message_access(message, user_id):
            return {'error': 'You do not have permission to access this voice note'}

        if not password:
            return {'error': 'Password required for decryption'}

        try:
            requester = User.query.get(user_id)
            requester_private_key = CryptoService.decrypt_private_key_with_password(
                requester.encrypted_private_key, password
            )

            is_uploader = message.sender_id == user_id
            if is_uploader:
                raw_aes_key = CryptoService.decrypt_group_key(voice_note.encryption_key, requester_private_key)
            elif message.recipient_type == 'user':
                if not voice_note.encryption_key_recipient:
                    return {'error': 'This voice note has no key wrapped for you — it may predate this fix'}
                raw_aes_key = CryptoService.decrypt_group_key(voice_note.encryption_key_recipient, requester_private_key)
            else:  # group
                from models import GroupMember
                member = GroupMember.query.filter_by(
                    group_id=message.recipient_id, user_id=user_id, is_active=True
                ).first()
                if not member or not member.encrypted_group_key:
                    return {'error': 'Your group key is missing — try leaving and rejoining the group'}
                raw_group_key = CryptoService.decrypt_group_key(member.encrypted_group_key, requester_private_key)
                if not voice_note.encryption_key_recipient or not voice_note.encryption_key_wrap_nonce:
                    return {'error': 'This voice note has no key wrapped for the group — it may predate this fix'}
                raw_aes_key = CryptoService.unwrap_key_with_raw_key(
                    voice_note.encryption_key_recipient,
                    voice_note.encryption_key_wrap_nonce,
                    raw_group_key
                )

            with open(voice_note.file_path, 'rb') as f:
                encrypted_data = f.read()

            decrypted_data = CryptoService.decrypt_file(
                encrypted_data,
                base64.b64encode(raw_aes_key).decode('utf-8'),
                voice_note.encryption_iv
            )

            return {'success': True, 'audio_data': decrypted_data}

        except Exception as e:
            logger.error(f"Download voice note error: {str(e)}")
            return {'error': f'Failed to download voice note: {str(e)}'}

    @staticmethod
    def get_voice_note_for_message(message_id: int, user_id: int) -> dict:
        """
        Look up the voice note attached to a message, for a client that
        already has the message and just needs the recording's id/duration
        to render a player.

        Args:
            message_id: Message ID
            user_id: Current user ID

        Returns:
            Dictionary with the voice note data or an error
        """
        message = Message.query.get(message_id)
        if not message or not VoiceService._check_message_access(message, user_id):
            return {'error': 'You do not have access to this message'}

        voice_note = VoiceNote.query.filter_by(message_id=message_id).first()
        if not voice_note:
            return {'error': 'No voice note attached to this message'}

        return {'success': True, 'voice_note': voice_note.to_dict()}