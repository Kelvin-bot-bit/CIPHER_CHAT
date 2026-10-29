# backend/services/file_service.py
import os
import uuid
import base64
from datetime import datetime
from werkzeug.utils import secure_filename
from models import File, Message, MessageAttachment, User
from extensions import db
from .crypto_service import CryptoService
from flask import current_app

class FileService:
    """Handles all file-related operations"""
    
    ALLOWED_EXTENSIONS = {
        'images': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'},
        'documents': {'pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx'},
        'videos': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'},
        'audio': {'mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a'},
        'archives': {'zip', 'rar', '7z', 'tar', 'gz'}
    }
    
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    
    @staticmethod
    def allowed_file(filename: str) -> bool:
        """Check if file extension is allowed"""
        if '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        for category in FileService.ALLOWED_EXTENSIONS.values():
            if ext in category:
                return True
        return False
    
    @staticmethod
    def get_file_category(filename: str) -> str:
        """Get the category of a file"""
        if '.' not in filename:
            return 'other'
        ext = filename.rsplit('.', 1)[1].lower()
        for category, extensions in FileService.ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return category
        return 'other'
    
    @staticmethod
    def upload_file(
        file_data: bytes,
        filename: str,
        uploader_id: int,
        message_id: int = None,
        mime_type: str = None,
        uploader_password: str = None
    ) -> dict:
        """
        Upload and encrypt a file
        
        Args:
            file_data: File data as bytes
            filename: Original filename
            uploader_id: ID of the user uploading
            message_id: ID of the message (if attached)
            mime_type: MIME type of the file
            uploader_password: Required only when message_id points to a
                group message — needed to unwrap the uploader's own copy
                of that group's key so the file's key can be wrapped with
                it too (see the encryption_key_recipient comment on the
                File model for why groups use a different wrap mechanism
                than direct messages).
        
        Returns:
            Dictionary with file data or error
        """
        # Validate file size
        if len(file_data) > FileService.MAX_FILE_SIZE:
            return {'error': f'File size exceeds maximum of {FileService.MAX_FILE_SIZE // 1024 // 1024}MB'}
        
        # Validate file type
        if not FileService.allowed_file(filename):
            return {'error': 'File type not allowed'}
        
        # Secure filename
        safe_filename = secure_filename(filename)
        if not safe_filename:
            safe_filename = str(uuid.uuid4())
        
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}_{safe_filename}"
        
        uploader = User.query.get(uploader_id)
        if not uploader:
            return {'error': 'Uploader not found'}
        
        # Resolve the linked message (if any) up front, since a group
        # attachment needs the uploader's password before we do anything
        # else — better to fail fast than encrypt+save a file we then
        # can't properly key-wrap.
        message = None
        recipient_user = None
        group = None
        group_member = None
        if message_id:
            message = Message.query.get(message_id)
            if not message:
                return {'error': 'Message not found'}
            if message.sender_id != uploader_id:
                return {'error': 'You can only attach files to your own messages'}
            
            if message.recipient_type == 'user':
                recipient_user = User.query.get(message.recipient_id)
            else:
                from models import Group, GroupMember
                group = Group.query.get(message.recipient_id)
                group_member = GroupMember.query.filter_by(
                    group_id=message.recipient_id, user_id=uploader_id, is_active=True
                ).first()
                if not group_member or not group_member.encrypted_group_key:
                    return {'error': 'Your group key is missing — try leaving and rejoining the group'}
                if not uploader_password:
                    return {'error': 'Password required to share a file in a group (needed to unwrap the group key)'}
        
        try:
            # Encrypt file with a fresh random AES key
            encrypted_data = CryptoService.encrypt_file(file_data)
            raw_aes_key = base64.b64decode(encrypted_data['encryption_key'])
            
            # Compute file hash
            file_hash = CryptoService.compute_file_hash(file_data)
            
            # Determine file path
            category = FileService.get_file_category(filename)
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], category)
            os.makedirs(upload_dir, exist_ok=True)
            
            file_path = os.path.join(upload_dir, unique_filename)
            
            # Save encrypted file
            with open(file_path, 'wb') as f:
                f.write(encrypted_data['encrypted_data'])
            
            # Wrap the AES key for the uploader — this replaces storing
            # the raw key directly, which meant anyone with DB access
            # could decrypt any file regardless of password.
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
            
            # Create file record
            file_record = File(
                uploader_id=uploader_id,
                file_name=safe_filename,
                file_hash=file_hash,
                file_path=file_path,
                file_size=len(file_data),
                mime_type=mime_type or 'application/octet-stream',
                encryption_key=wrapped_for_uploader,
                encryption_key_recipient=wrapped_for_recipient,
                encryption_key_wrap_nonce=wrap_nonce,
                encryption_iv=encrypted_data['nonce'],
                is_encrypted=True
            )
            db.session.add(file_record)
            db.session.commit()
            
            # Attach to message if provided
            if message_id:
                attachment = MessageAttachment(
                    message_id=message_id,
                    file_id=file_record.id
                )
                db.session.add(attachment)
                
                # Update message
                if message:
                    message.file_url = file_path
                    message.file_name = safe_filename
                    message.file_size = len(file_data)
                    message.mime_type = mime_type
                
                db.session.commit()
            
            return {
                'success': True,
                'file': file_record.to_dict(),
                'file_path': file_path,
                'file_hash': file_hash
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to upload file: {str(e)}'}
    
    @staticmethod
    def download_file(file_id: int, user_id: int, password: str) -> dict:
        """
        Download and decrypt a file
        
        Args:
            file_id: ID of the file
            user_id: ID of the user downloading
            password: Requester's password — needed to unlock their
                private key (or, for a group file, their copy of the
                group key) to unwrap the file's AES key. Previously this
                parameter existed on the route but was never actually
                used here; the key was stored in plaintext so nothing
                needed unlocking. That's fixed now, so this is load-
                bearing.
        
        Returns:
            Dictionary with file data or error
        """
        file_record = File.query.get(file_id)
        if not file_record:
            return {'error': 'File not found'}
        
        is_uploader = file_record.uploader_id == user_id
        message = None
        attachment = MessageAttachment.query.filter_by(file_id=file_id).first()
        if attachment:
            message = Message.query.get(attachment.message_id)
        
        has_access = is_uploader
        if not has_access and message:
            if message.recipient_type == 'user':
                has_access = message.sender_id == user_id or message.recipient_id == user_id
            elif message.recipient_type == 'group':
                from .group_service import GroupService
                has_access = GroupService.is_member(user_id, message.recipient_id)
        
        if not has_access:
            return {'error': 'You do not have permission to download this file'}
        
        if not password:
            return {'error': 'Password required for decryption'}
        
        try:
            requester = User.query.get(user_id)
            requester_private_key = CryptoService.decrypt_private_key_with_password(
                requester.encrypted_private_key, password
            )
            
            if is_uploader:
                raw_aes_key = CryptoService.decrypt_group_key(file_record.encryption_key, requester_private_key)
            elif message.recipient_type == 'user':
                if not file_record.encryption_key_recipient:
                    return {'error': 'This file has no key wrapped for you — it may predate this fix'}
                raw_aes_key = CryptoService.decrypt_group_key(file_record.encryption_key_recipient, requester_private_key)
            else:  # group
                from models import GroupMember
                member = GroupMember.query.filter_by(
                    group_id=message.recipient_id, user_id=user_id, is_active=True
                ).first()
                if not member or not member.encrypted_group_key:
                    return {'error': 'Your group key is missing — try leaving and rejoining the group'}
                raw_group_key = CryptoService.decrypt_group_key(member.encrypted_group_key, requester_private_key)
                if not file_record.encryption_key_recipient or not file_record.encryption_key_wrap_nonce:
                    return {'error': 'This file has no key wrapped for the group — it may predate this fix'}
                raw_aes_key = CryptoService.unwrap_key_with_raw_key(
                    file_record.encryption_key_recipient,
                    file_record.encryption_key_wrap_nonce,
                    raw_group_key
                )
            
            # Read encrypted file
            with open(file_record.file_path, 'rb') as f:
                encrypted_data = f.read()
            
            # Decrypt file
            decrypted_data = CryptoService.decrypt_file(
                encrypted_data,
                base64.b64encode(raw_aes_key).decode('utf-8'),
                file_record.encryption_iv
            )
            
            # Increment download count
            file_record.increment_download_count()
            
            return {
                'success': True,
                'file_data': decrypted_data,
                'file_name': file_record.file_name,
                'mime_type': file_record.mime_type,
                'file_size': file_record.file_size
            }
            
        except Exception as e:
            return {'error': f'Failed to download file: {str(e)}'}
    
    @staticmethod
    def delete_file(file_id: int, user_id: int) -> dict:
        """
        Delete a file
        
        Args:
            file_id: ID of the file
            user_id: ID of the user deleting
        
        Returns:
            Dictionary with success or error
        """
        file_record = File.query.get(file_id)
        if not file_record:
            return {'error': 'File not found'}
        
        # Only uploader can delete
        if file_record.uploader_id != user_id:
            return {'error': 'You do not have permission to delete this file'}
        
        try:
            # Delete physical file
            if os.path.exists(file_record.file_path):
                os.remove(file_record.file_path)
            
            # Delete database record
            db.session.delete(file_record)
            db.session.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to delete file: {str(e)}'}
    
    @staticmethod
    def get_user_files(user_id: int) -> dict:
        """
        Get all files uploaded by a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with files list
        """
        files = File.query.filter_by(uploader_id=user_id).order_by(
            File.created_at.desc()
        ).all()
        
        return {
            'success': True,
            'files': [f.to_dict() for f in files],
            'total': len(files)
        }
    
    @staticmethod
    def get_message_files(message_id: int, user_id: int) -> dict:
        """
        Get all files attached to a message
        
        Args:
            message_id: Message ID
            user_id: Current user ID
        
        Returns:
            Dictionary with files list or error
        """
        message = Message.query.get(message_id)
        if not message:
            return {'error': 'Message not found'}
        
        # Check access
        has_access = False
        if message.recipient_type == 'user':
            has_access = message.sender_id == user_id or message.recipient_id == user_id
        elif message.recipient_type == 'group':
            from .group_service import GroupService
            has_access = GroupService.is_member(user_id, message.recipient_id)
        
        if not has_access:
            return {'error': 'You do not have access to this message'}
        
        attachments = MessageAttachment.query.filter_by(message_id=message_id).all()
        files = []
        for attachment in attachments:
            file_record = File.query.get(attachment.file_id)
            if file_record:
                files.append(file_record.to_dict())
        
        return {
            'success': True,
            'files': files,
            'total': len(files)
        }