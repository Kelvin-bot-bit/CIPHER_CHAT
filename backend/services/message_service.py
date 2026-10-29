# backend/services/message_service.py
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import and_, or_
from models import Message, MessageStatus, MessageReaction, User, Group, GroupMember
from extensions import db
from .crypto_service import CryptoService
from .notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)

class MessageService:
    """Handles all message operations"""
    
    @staticmethod
    def send_message(
        sender_id: int,
        recipient_id: int,
        recipient_type: str,
        plaintext: str,
        sender_private_key_pem: str,
        recipient_public_key_pem: str = None,
        reply_to_message_id: int = None,
        message_type: str = 'text',
        expires_in_seconds: int = None
    ) -> dict:
        """
        Send an encrypted message
        
        Args:
            sender_id: Sender's user ID
            recipient_id: Recipient ID (user or group)
            recipient_type: 'user' or 'group'
            plaintext: Message text
            sender_private_key_pem: Sender's private key
            recipient_public_key_pem: Recipient's public key (for user messages)
            reply_to_message_id: ID of message being replied to
            message_type: Type of message
        
        Returns:
            Dictionary with message data or error
        """
        try:
            # Validate sender
            sender = User.query.get(sender_id)
            if not sender or not sender.is_active:
                return {'error': 'Sender not found or inactive'}
            
            # Validate recipient
            if recipient_type == 'user':
                recipient = User.query.get(recipient_id)
                if not recipient or not recipient.is_active:
                    return {'error': 'Recipient not found or inactive'}
                
                # Check if users are friends
                from .friend_service import FriendService
                if not FriendService.are_friends(sender_id, recipient_id):
                    return {'error': 'You can only send messages to friends'}
                
                recipient_public_key = recipient_public_key_pem or recipient.public_key
                
                # Encrypt message — wrapping the AES key for both the
                # recipient AND the sender's own public key, so the sender
                # can still decrypt their own sent messages later (a plain
                # single-recipient wrap means the sender's private key can
                # never unwrap it, since it was only ever encrypted for the
                # recipient's key).
                encrypted_data = CryptoService.encrypt_message_dual(
                    plaintext,
                    recipient_public_key,
                    sender.public_key,
                    sender_private_key_pem
                )
                
                # Create message
                message = Message(
                    sender_id=sender_id,
                    recipient_type='user',
                    recipient_id=recipient_id,
                    encrypted_message=encrypted_data['encrypted_message'],
                    encrypted_aes_key=encrypted_data['encrypted_aes_key'],
                    encrypted_aes_key_sender=encrypted_data['encrypted_aes_key_sender'],
                    nonce=encrypted_data['nonce'],
                    tag=encrypted_data['tag'],
                    digital_signature=encrypted_data['signature'],
                    message_type=message_type,
                    reply_to_message_id=reply_to_message_id,
                    expires_at=(datetime.utcnow() + timedelta(seconds=expires_in_seconds)) if expires_in_seconds else None
                )
                
                db.session.add(message)
                db.session.commit()
                
                # Create message status for recipient
                message_status = MessageStatus(
                    message_id=message.id,
                    user_id=recipient_id,
                    status='delivered',
                    delivered_at=datetime.utcnow()
                )
                db.session.add(message_status)
                db.session.commit()
                
                # Create notification for recipient
                NotificationService.create_notification(
                    user_id=recipient_id,
                    notification_type='message',
                    sender_id=sender_id,
                    message=f'New message from {sender.username}',
                    reference_id=message.id
                )
                
                return {
                    'success': True,
                    'message_id': message.id,
                    'message': message.to_dict(include_encrypted=True)
                }
                
            elif recipient_type == 'group':
                # Handle group message
                return MessageService.send_group_message(
                    sender_id,
                    recipient_id,
                    plaintext,
                    sender_private_key_pem,
                    reply_to_message_id,
                    message_type,
                    expires_in_seconds
                )
            
            else:
                return {'error': 'Invalid recipient type'}
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Send message error: {str(e)}", exc_info=True)
            return {'error': f'Failed to send message: {str(e)}'}
    
    @staticmethod
    def send_group_message(
        sender_id: int,
        group_id: int,
        plaintext: str,
        sender_private_key_pem: str,
        reply_to_message_id: int = None,
        message_type: str = 'text',
        expires_in_seconds: int = None
    ) -> dict:
        """Send a message to a group"""
        # Validate group
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if sender is a member
        if not group.is_member(sender_id):
            return {'error': 'You are not a member of this group'}
        
        # Get group members
        members = group.get_active_members()
        if not members:
            return {'error': 'Group has no active members'}
        
        # Get the sender's own wrapped copy of the group key, and unwrap it
        # with their private key. This replaces a previous version of this
        # method that passed group.group_key (an RSA-*encrypted* blob, not
        # a public key) straight into the single-recipient encrypt_message
        # helper — that raised on every call, since the blob isn't valid
        # PEM. Every member now holds their own wrapped copy via
        # GroupMember.encrypted_group_key instead.
        sender_member = GroupMember.query.filter_by(
            group_id=group_id, user_id=sender_id, is_active=True
        ).first()
        if not sender_member or not sender_member.encrypted_group_key:
            return {'error': 'Your group key is missing — try leaving and rejoining the group'}
        
        try:
            raw_group_key = CryptoService.decrypt_group_key(
                sender_member.encrypted_group_key,
                sender_private_key_pem
            )
        except Exception as e:
            return {'error': f'Failed to unlock group key: {str(e)}'}
        
        # Encrypt the message directly with the group's raw key
        encrypted_data = CryptoService.encrypt_with_raw_key(
            plaintext,
            raw_group_key,
            sender_private_key_pem
        )
        
        # Create message
        message = Message(
            sender_id=sender_id,
            recipient_type='group',
            recipient_id=group_id,
            encrypted_message=encrypted_data['encrypted_message'],
            # Stored for reference/audit only — group members don't need
            # this to decrypt (they use their own encrypted_group_key), so
            # this is just the sender's own wrapped copy, not a fresh
            # per-message wrap the way direct messages use this column.
            encrypted_aes_key=sender_member.encrypted_group_key,
            nonce=encrypted_data['nonce'],
            tag=encrypted_data['tag'],
            digital_signature=encrypted_data['signature'],
            message_type=message_type,
            reply_to_message_id=reply_to_message_id,
            expires_at=(datetime.utcnow() + timedelta(seconds=expires_in_seconds)) if expires_in_seconds else None
        )
        
        db.session.add(message)
        db.session.commit()
        
        # Create message status for each member
        for member in members:
            if member.user_id != sender_id:
                message_status = MessageStatus(
                    message_id=message.id,
                    user_id=member.user_id,
                    status='delivered',
                    delivered_at=datetime.utcnow()
                )
                db.session.add(message_status)
        
        db.session.commit()
        
        # Create notifications for members
        for member in members:
            if member.user_id != sender_id:
                NotificationService.create_notification(
                    user_id=member.user_id,
                    notification_type='message',
                    sender_id=sender_id,
                    message=f'New message in group "{group.group_name}"',
                    reference_id=message.id
                )
        
        return {
            'success': True,
            'message_id': message.id,
            'message': message.to_dict(include_encrypted=True)
        }
    
    @staticmethod
    def get_messages(
        user_id: int,
        chat_id: int,
        chat_type: str = 'user',
        limit: int = 50,
        offset: int = 0
    ) -> dict:
        """
        Get messages for a chat - Returns SQLAlchemy model objects
        
        Args:
            user_id: Current user ID
            chat_id: Chat ID (user or group)
            chat_type: 'user' or 'group'
            limit: Number of messages to return
            offset: Pagination offset
        
        Returns:
            Dictionary with messages (model objects), chat info, and total count
        """
        try:
            if chat_type == 'user':
                # Get direct messages between two users (as model objects).
                # Ordered DESC + LIMIT/OFFSET to get the most recent window
                # first (offset=0 → newest N, offset=N → the next-older N,
                # and so on for infinite scroll) — then reversed back to
                # ascending order below, since callers display oldest-to-
                # newest. The previous version ordered ASC before applying
                # LIMIT/OFFSET, which meant offset=0 actually returned the
                # OLDEST messages in the conversation, not the newest —
                # anyone with more than `limit` messages could never see
                # their recent ones.
                messages = Message.query.filter(
                    or_(
                        and_(
                            Message.sender_id == user_id,
                            Message.recipient_id == chat_id,
                            Message.recipient_type == 'user'
                        ),
                        and_(
                            Message.sender_id == chat_id,
                            Message.recipient_id == user_id,
                            Message.recipient_type == 'user'
                        )
                    ),
                    Message.is_deleted == False,
                    or_(Message.expires_at.is_(None), Message.expires_at > datetime.utcnow())
                ).order_by(
                    Message.created_at.desc()
                ).limit(limit).offset(offset).all()
                messages = list(reversed(messages))
                
                # Get total count
                total = Message.query.filter(
                    or_(
                        and_(
                            Message.sender_id == user_id,
                            Message.recipient_id == chat_id,
                            Message.recipient_type == 'user'
                        ),
                        and_(
                            Message.sender_id == chat_id,
                            Message.recipient_id == user_id,
                            Message.recipient_type == 'user'
                        )
                    ),
                    Message.is_deleted == False
                ).count()
                
                # Get user info
                chat_user = User.query.get(chat_id)
                if not chat_user:
                    return {'error': 'User not found'}
                
                # Mark messages as read for this user
                for message in messages:
                    if message.recipient_id == user_id and message.recipient_type == 'user':
                        try:
                            message.mark_as_read(user_id)
                        except Exception as e:
                            logger.error(f"Error marking message {message.id} as read: {e}")
                
                return {
                    'success': True,
                    'messages': messages,  # Return model objects
                    'chat_info': chat_user.to_dict(),
                    'total': total
                }
                
            elif chat_type == 'group':
                # Same DESC-then-reverse fix as the direct-message branch
                # above.
                messages = Message.query.filter(
                    Message.recipient_id == chat_id,
                    Message.recipient_type == 'group',
                    Message.is_deleted == False,
                    or_(Message.expires_at.is_(None), Message.expires_at > datetime.utcnow())
                ).order_by(
                    Message.created_at.desc()
                ).limit(limit).offset(offset).all()
                messages = list(reversed(messages))
                
                # Get total count
                total = Message.query.filter(
                    Message.recipient_id == chat_id,
                    Message.recipient_type == 'group',
                    Message.is_deleted == False
                ).count()
                
                # Check if user is a member
                group = Group.query.get(chat_id)
                if not group or not group.is_member(user_id):
                    return {'error': 'You are not a member of this group'}
                
                # Mark messages as read for this user
                for message in messages:
                    try:
                        message.mark_as_read(user_id)
                    except Exception as e:
                        logger.error(f"Error marking message {message.id} as read: {e}")
                
                # Update last read message
                if messages:
                    member = GroupMember.query.filter_by(
                        group_id=chat_id,
                        user_id=user_id,
                        is_active=True
                    ).first()
                    if member:
                        member.last_read_message_id = messages[-1].id
                        db.session.commit()
                
                return {
                    'success': True,
                    'messages': messages,  # Return model objects
                    'chat_info': group.to_dict(),
                    'total': total
                }
            
            else:
                return {'error': 'Invalid chat type. Must be "user" or "group"'}
                
        except Exception as e:
            logger.error(f"Get messages error: {str(e)}", exc_info=True)
            return {'error': f'Failed to get messages: {str(e)}'}
    
    @staticmethod
    def decrypt_messages(
        messages: List[Message],
        user_private_key_pem: str,
        sender_public_key_pem: str = None
    ) -> List[dict]:
        """
        Decrypt a list of messages
        
        Args:
            messages: List of Message objects
            user_private_key_pem: User's private key
            sender_public_key_pem: Sender's public key (for user messages)
        
        Returns:
            List of decrypted message dictionaries
        """
        decrypted_messages = []
        
        for message in messages:
            try:
                encrypted_data = {
                    'encrypted_message': message.encrypted_message,
                    'encrypted_aes_key': message.encrypted_aes_key,
                    'nonce': message.nonce,
                    'signature': message.digital_signature
                }
                
                # Get sender's public key if not provided
                if not sender_public_key_pem:
                    sender = User.query.get(message.sender_id)
                    if sender:
                        sender_public_key_pem = sender.public_key
                
                # Decrypt message
                decrypted = CryptoService.decrypt_message(
                    encrypted_data,
                    user_private_key_pem,
                    sender_public_key_pem
                )
                
                decrypted_messages.append({
                    'id': message.id,
                    'sender_id': message.sender_id,
                    'message': decrypted.get('decrypted_message'),
                    'is_valid_signature': decrypted.get('is_valid_signature', False),
                    'created_at': message.created_at.isoformat(),
                    'message_type': message.message_type,
                    'is_edited': message.is_edited,
                    'is_deleted': message.is_deleted,
                    'file_url': message.file_url,
                    'file_name': message.file_name,
                    'reactions': message.get_reaction_summary() if hasattr(message, 'get_reaction_summary') else {}
                })
            except Exception as e:
                logger.error(f"Error decrypting message {message.id}: {str(e)}")
                decrypted_messages.append({
                    'id': message.id,
                    'sender_id': message.sender_id,
                    'message': '[Unable to decrypt]',
                    'is_valid_signature': False,
                    'created_at': message.created_at.isoformat(),
                    'message_type': message.message_type,
                    'is_edited': message.is_edited,
                    'is_deleted': message.is_deleted,
                    'file_url': message.file_url,
                    'file_name': message.file_name,
                    'reactions': {}
                })
        
        return decrypted_messages
    
    @staticmethod
    def edit_message(
        message_id: int,
        user_id: int,
        new_plaintext: str,
        user_private_key_pem: str,
        recipient_public_key_pem: str = None
    ) -> dict:
        """
        Edit an existing message
        
        Args:
            message_id: ID of message to edit
            user_id: Current user ID
            new_plaintext: New message text
            user_private_key_pem: User's private key
            recipient_public_key_pem: Recipient's public key
        
        Returns:
            Dictionary with success or error
        """
        message = Message.query.get(message_id)
        if not message:
            return {'error': 'Message not found'}
        
        # Check if user is the sender
        if message.sender_id != user_id:
            return {'error': 'You can only edit your own messages'}
        
        # Check if message is too old to edit (e.g., 5 minutes)
        time_diff = datetime.utcnow() - message.created_at
        if time_diff.seconds > 300:  # 5 minutes
            return {'error': 'Message can only be edited within 5 minutes of sending'}
        
        try:
            if message.recipient_type == 'user':
                if not recipient_public_key_pem:
                    recipient = User.query.get(message.recipient_id)
                    if recipient:
                        recipient_public_key_pem = recipient.public_key
                
                sender = User.query.get(user_id)
                encrypted_data = CryptoService.encrypt_message_dual(
                    new_plaintext,
                    recipient_public_key_pem,
                    sender.public_key,
                    user_private_key_pem
                )
                message.encrypted_aes_key = encrypted_data['encrypted_aes_key']
                message.encrypted_aes_key_sender = encrypted_data['encrypted_aes_key_sender']
            
            else:  # group
                # Same fix as send_group_message: use the editor's own
                # wrapped copy of the group key rather than passing the
                # group's RSA-encrypted key blob somewhere a PEM public
                # key is expected, which raised on every previous attempt
                # to edit a group message.
                sender_member = GroupMember.query.filter_by(
                    group_id=message.recipient_id, user_id=user_id, is_active=True
                ).first()
                if not sender_member or not sender_member.encrypted_group_key:
                    return {'error': 'Your group key is missing — try leaving and rejoining the group'}
                
                raw_group_key = CryptoService.decrypt_group_key(
                    sender_member.encrypted_group_key,
                    user_private_key_pem
                )
                encrypted_data = CryptoService.encrypt_with_raw_key(
                    new_plaintext,
                    raw_group_key,
                    user_private_key_pem
                )
                message.encrypted_aes_key = sender_member.encrypted_group_key
            
            # Update message
            message.encrypted_message = encrypted_data['encrypted_message']
            message.nonce = encrypted_data['nonce']
            message.tag = encrypted_data['tag']
            message.digital_signature = encrypted_data['signature']
            message.is_edited = True
            message.edited_at = datetime.utcnow()
            
            db.session.commit()
            
            return {
                'success': True,
                'message': message.to_dict(include_encrypted=True)
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Edit message error: {str(e)}", exc_info=True)
            return {'error': f'Failed to edit message: {str(e)}'}
    
    @staticmethod
    def delete_message(
        message_id: int,
        user_id: int,
        delete_for_everyone: bool = False
    ) -> dict:
        """
        Delete a message
        
        Args:
            message_id: ID of message to delete
            user_id: Current user ID
            delete_for_everyone: If True, delete for all users
        
        Returns:
            Dictionary with success or error
        """
        message = Message.query.get(message_id)
        if not message:
            return {'error': 'Message not found'}
        
        # Check permissions
        if delete_for_everyone:
            # Only sender can delete for everyone
            if message.sender_id != user_id:
                return {'error': 'You can only delete your own messages'}
            
            # Soft delete for everyone
            message.is_deleted = True
            db.session.commit()
            
            return {'success': True, 'deleted_for_everyone': True}
        else:
            # Delete for specific user
            status = message.get_status_for_user(user_id)
            if status:
                status.status = 'deleted'
                db.session.commit()
                return {'success': True, 'deleted_for_everyone': False}
            else:
                return {'error': 'Message not found for this user'}
    
    @staticmethod
    def add_reaction(
        message_id: int,
        user_id: int,
        reaction: str
    ) -> dict:
        """
        Add a reaction to a message
        
        Args:
            message_id: ID of message
            user_id: Current user ID
            reaction: Emoji reaction
        
        Returns:
            Dictionary with success or error
        """
        message = Message.query.get(message_id)
        if not message:
            return {'error': 'Message not found'}
        
        # Check if user can access the message
        if message.recipient_type == 'user':
            if message.sender_id != user_id and message.recipient_id != user_id:
                return {'error': 'You cannot react to this message'}
        elif message.recipient_type == 'group':
            group = Group.query.get(message.recipient_id)
            if not group or not group.is_member(user_id):
                return {'error': 'You are not a member of this group'}
        
        try:
            reaction_obj = message.add_reaction(user_id, reaction)
            
            return {
                'success': True,
                'reaction': reaction_obj.to_dict() if reaction_obj else None,
                'summary': message.get_reaction_summary()
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Add reaction error: {str(e)}", exc_info=True)
            return {'error': f'Failed to add reaction: {str(e)}'}
    
    @staticmethod
    def get_unread_count(user_id: int) -> dict:
        """
        Get unread message count for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with unread counts
        """
        try:
            # Get unread direct messages
            direct_unread = MessageStatus.query.join(
                Message, Message.id == MessageStatus.message_id
            ).filter(
                MessageStatus.user_id == user_id,
                MessageStatus.status != 'read',
                Message.recipient_type == 'user',
                Message.is_deleted == False
            ).count()
            
            # Get unread group messages
            group_unread = MessageStatus.query.join(
                Message, Message.id == MessageStatus.message_id
            ).filter(
                MessageStatus.user_id == user_id,
                MessageStatus.status != 'read',
                Message.recipient_type == 'group',
                Message.is_deleted == False
            ).count()
            
            return {
                'total': direct_unread + group_unread,
                'direct': direct_unread,
                'groups': group_unread
            }
        except Exception as e:
            logger.error(f"Get unread count error: {str(e)}", exc_info=True)
            return {'error': f'Failed to get unread count: {str(e)}'}

    @staticmethod
    def get_unread_count_by_chat(user_id: int) -> dict:
        """
        Get unread message counts broken down per conversation, for showing
        a badge on each item in a chat list before it's opened.
        get_unread_count() above only returns a global total, which can't
        drive a per-chat badge — this groups the same MessageStatus rows by
        the other party (sender_id for a direct chat, recipient_id/group id
        for a group chat) instead of just counting them.

        Args:
            user_id: User ID

        Returns:
            Dictionary with a list of {chat_type, chat_id, unread_count}
        """
        try:
            direct_rows = db.session.query(
                Message.sender_id, db.func.count(MessageStatus.id)
            ).join(
                MessageStatus, MessageStatus.message_id == Message.id
            ).filter(
                MessageStatus.user_id == user_id,
                MessageStatus.status != 'read',
                Message.recipient_type == 'user',
                Message.recipient_id == user_id,
                Message.is_deleted == False
            ).group_by(Message.sender_id).all()

            group_rows = db.session.query(
                Message.recipient_id, db.func.count(MessageStatus.id)
            ).join(
                MessageStatus, MessageStatus.message_id == Message.id
            ).filter(
                MessageStatus.user_id == user_id,
                MessageStatus.status != 'read',
                Message.recipient_type == 'group',
                Message.is_deleted == False
            ).group_by(Message.recipient_id).all()

            chats = [
                {'chat_type': 'user', 'chat_id': sender_id, 'unread_count': count}
                for sender_id, count in direct_rows
            ]
            chats += [
                {'chat_type': 'group', 'chat_id': recipient_id, 'unread_count': count}
                for recipient_id, count in group_rows
            ]

            return {'chats': chats}
        except Exception as e:
            logger.error(f"Get unread count by chat error: {str(e)}", exc_info=True)
            return {'error': f'Failed to get unread count by chat: {str(e)}'}