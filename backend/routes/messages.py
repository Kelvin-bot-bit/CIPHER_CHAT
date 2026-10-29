# backend/routes/messages.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from models import User, Message, GroupMember
from services.message_service import MessageService
from services.crypto_service import CryptoService
from services.key_management import KeyManagementService
from extensions import db
import logging

messages_bp = Blueprint('messages', __name__)
logger = logging.getLogger(__name__)

@messages_bp.route('/send', methods=['POST'])
@jwt_required()
def send_message():
    """
    Send an encrypted message
    ---
    tags:
      - Messages
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - recipient_id
            - recipient_type
            - message
            - password
          properties:
            recipient_id:
              type: integer
            recipient_type:
              type: string
              enum: ['user', 'group']
            message:
              type: string
            password:
              type: string
            reply_to_message_id:
              type: integer
            message_type:
              type: string
              enum: ['text', 'image', 'file', 'voice', 'video', 'audio']
            expires_in_seconds:
              type: integer
              description: If set, the message is deleted this many seconds after being sent (disappearing messages)
    responses:
      200:
        description: Message sent successfully
      400:
        description: Validation error
      401:
        description: Unauthorized
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['recipient_id', 'recipient_type', 'message', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate message content
        if not data.get('message') or len(data['message'].strip()) < 1:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Get user's private key
        private_key_result = KeyManagementService.get_user_private_key(user_id, data['password'])
        if not private_key_result.get('success'):
            return jsonify({'error': private_key_result.get('error')}), 400
        
        sender_private_key = private_key_result['private_key']
        
        # Get recipient info for user messages
        recipient_public_key = None
        if data['recipient_type'] == 'user':
            recipient = User.query.get(data['recipient_id'])
            if not recipient:
                return jsonify({'error': 'Recipient not found'}), 404
            recipient_public_key = recipient.public_key
        
        # Send message
        result = MessageService.send_message(
            sender_id=user_id,
            recipient_id=data['recipient_id'],
            recipient_type=data['recipient_type'],
            plaintext=data['message'],
            sender_private_key_pem=sender_private_key,
            recipient_public_key_pem=recipient_public_key,
            reply_to_message_id=data.get('reply_to_message_id'),
            message_type=data.get('message_type', 'text'),
            expires_in_seconds=data.get('expires_in_seconds')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Message sent successfully',
            'message_id': result['message_id']
        }), 200
        
    except Exception as e:
        logger.error(f"Send message error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to send message'}), 500

@messages_bp.route('/chat/<int:chat_id>', methods=['GET'])
@jwt_required()
def get_messages(chat_id):
    """
    Get messages for a chat
    ---
    tags:
      - Messages
    parameters:
      - name: chat_id
        in: path
        required: true
        type: integer
      - name: chat_type
        in: query
        required: true
        type: string
        enum: ['user', 'group']
      - name: limit
        in: query
        type: integer
        default: 50
      - name: offset
        in: query
        type: integer
        default: 0
      - name: password
        in: query
        required: true
        type: string
    responses:
      200:
        description: Messages retrieved successfully
      401:
        description: Unauthorized
    """
    try:
        user_id = int(get_jwt_identity())
        chat_type = request.args.get('chat_type', 'user')
        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))
        password = request.args.get('password')
        
        logger.info(f"Getting messages for user {user_id}, chat {chat_id}, type {chat_type}")
        
        if not password:
            return jsonify({'error': 'Password required for decryption'}), 400
        
        # Get user's private key
        private_key_result = KeyManagementService.get_user_private_key(user_id, password)
        if not private_key_result.get('success'):
            return jsonify({'error': private_key_result.get('error')}), 400
        
        user_private_key = private_key_result['private_key']
        
        # Get messages
        result = MessageService.get_messages(
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            limit=limit,
            offset=offset
        )
        
        if result.get('error'):
            logger.error(f"Message service error: {result['error']}")
            return jsonify({'error': result['error']}), 400
        
        # Get messages (should be model objects from service)
        messages = result.get('messages', [])
        decrypted_messages = []
        
        # For a group chat, the viewer's own wrapped copy of the group key
        # is the same for every message in this chat, so unwrap it once
        # here rather than repeating an RSA decrypt per message.
        raw_group_key = None
        if chat_type == 'group':
            viewer_member = GroupMember.query.filter_by(
                group_id=chat_id, user_id=user_id, is_active=True
            ).first()
            if viewer_member and viewer_member.encrypted_group_key:
                try:
                    raw_group_key = CryptoService.decrypt_group_key(
                        viewer_member.encrypted_group_key,
                        user_private_key
                    )
                except Exception as e:
                    logger.error(f"Failed to unwrap group key for user {user_id} in group {chat_id}: {str(e)}")
        
        for msg in messages:
            try:
                # Ensure msg is a Message model object
                if not hasattr(msg, 'encrypted_message'):
                    logger.error(f"Invalid message object: {type(msg)}")
                    continue
                
                # Get sender
                sender = User.query.get(msg.sender_id)
                if not sender:
                    logger.error(f"Sender not found for message {msg.id}")
                    continue
                
                if msg.recipient_type == 'group':
                    if raw_group_key is None:
                        raise ValueError('Group key unavailable')
                    encrypted_data = {
                        'encrypted_message': msg.encrypted_message,
                        'nonce': msg.nonce,
                        'signature': msg.digital_signature
                    }
                    decrypted = CryptoService.decrypt_with_raw_key(
                        encrypted_data,
                        raw_group_key,
                        sender.public_key
                    )
                else:
                    # Direct message: a sender re-reading their own sent
                    # history needs encrypted_aes_key_sender (wrapped for
                    # their own public key) — encrypted_aes_key was only
                    # ever wrapped for the recipient, so the sender's
                    # private key can't unwrap that copy. Older messages
                    # sent before this fix won't have a sender copy and
                    # will still show as undecryptable for the sender —
                    # that's expected, not a new bug.
                    if msg.sender_id == user_id and msg.encrypted_aes_key_sender:
                        aes_key_field = msg.encrypted_aes_key_sender
                    else:
                        aes_key_field = msg.encrypted_aes_key
                    
                    encrypted_data = {
                        'encrypted_message': msg.encrypted_message,
                        'encrypted_aes_key': aes_key_field,
                        'nonce': msg.nonce,
                        'signature': msg.digital_signature
                    }
                    
                    decrypted = CryptoService.decrypt_message(
                        encrypted_data,
                        user_private_key,
                        sender.public_key
                    )
                
                decrypted_messages.append({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'sender_username': sender.username,
                    'message': decrypted.get('decrypted_message', 'Unable to decrypt'),
                    'is_valid_signature': decrypted.get('is_valid_signature', False),
                    'created_at': msg.created_at.isoformat() + 'Z',
                    'message_type': msg.message_type,
                    'is_edited': msg.is_edited,
                    'is_deleted': msg.is_deleted,
                    'file_url': msg.file_url,
                    'file_name': msg.file_name,
                    'expires_at': msg.expires_at.isoformat() if msg.expires_at else None,
                    'reactions': msg.get_reaction_summary() if hasattr(msg, 'get_reaction_summary') else {}
                })
                
            except Exception as e:
                logger.error(f"Error decrypting message: {str(e)}", exc_info=True)
                # Add a placeholder for the failed message
                decrypted_messages.append({
                    'id': msg.id if hasattr(msg, 'id') else None,
                    'sender_id': msg.sender_id if hasattr(msg, 'sender_id') else None,
                    'sender_username': 'Unknown',
                    'message': '[Error decrypting message]',
                    'is_valid_signature': False,
                    'created_at': (msg.created_at.isoformat() + 'Z') if hasattr(msg, 'created_at') else (datetime.utcnow().isoformat() + 'Z'),
                    'message_type': 'text',
                    'is_edited': False,
                    'is_deleted': False,
                    'file_url': None,
                    'file_name': None,
                    'reactions': {}
                })
        
        return jsonify({
            'messages': decrypted_messages,
            'chat_info': result.get('chat_info'),
            'total': result.get('total', 0),
            'limit': limit,
            'offset': offset
        }), 200
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}", exc_info=True)
        return jsonify({'error': f'Failed to get messages: {str(e)}'}), 500

@messages_bp.route('/<int:message_id>', methods=['PUT'])
@jwt_required()
def edit_message(message_id):
    """
    Edit a message
    ---
    tags:
      - Messages
    parameters:
      - name: message_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - message
            - password
          properties:
            message:
              type: string
            password:
              type: string
    responses:
      200:
        description: Message edited successfully
      400:
        description: Validation error
      401:
        description: Unauthorized
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('message'):
            return jsonify({'error': 'Message content is required'}), 400
        
        if not data.get('password'):
            return jsonify({'error': 'Password required'}), 400
        
        # Get user's private key
        private_key_result = KeyManagementService.get_user_private_key(user_id, data['password'])
        if not private_key_result.get('success'):
            return jsonify({'error': private_key_result.get('error')}), 400
        
        # Edit message
        result = MessageService.edit_message(
            message_id=message_id,
            user_id=user_id,
            new_plaintext=data['message'],
            user_private_key_pem=private_key_result['private_key']
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Message edited successfully',
            'message_id': message_id
        }), 200
        
    except Exception as e:
        logger.error(f"Edit message error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to edit message'}), 500

@messages_bp.route('/<int:message_id>', methods=['DELETE'])
@jwt_required()
def delete_message(message_id):
    """
    Delete a message
    ---
    tags:
      - Messages
    parameters:
      - name: message_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            delete_for_everyone:
              type: boolean
              default: false
    responses:
      200:
        description: Message deleted successfully
      401:
        description: Unauthorized
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        delete_for_everyone = data.get('delete_for_everyone', False)
        
        result = MessageService.delete_message(
            message_id=message_id,
            user_id=user_id,
            delete_for_everyone=delete_for_everyone
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Message deleted successfully',
            'deleted_for_everyone': result.get('deleted_for_everyone', False)
        }), 200
        
    except Exception as e:
        logger.error(f"Delete message error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to delete message'}), 500

@messages_bp.route('/<int:message_id>/reaction', methods=['POST'])
@jwt_required()
def add_reaction(message_id):
    """
    Add reaction to a message
    ---
    tags:
      - Messages
    parameters:
      - name: message_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - reaction
          properties:
            reaction:
              type: string
              description: Emoji reaction
    responses:
      200:
        description: Reaction added successfully
      400:
        description: Validation error
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('reaction'):
            return jsonify({'error': 'Reaction is required'}), 400
        
        result = MessageService.add_reaction(
            message_id=message_id,
            user_id=user_id,
            reaction=data['reaction']
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Reaction added successfully',
            'reaction': result.get('reaction'),
            'summary': result.get('summary')
        }), 200
        
    except Exception as e:
        logger.error(f"Add reaction error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to add reaction'}), 500

@messages_bp.route('/unread', methods=['GET'])
@jwt_required()
def get_unread_count():
    """
    Get unread message count
    ---
    tags:
      - Messages
    responses:
      200:
        description: Unread count retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = MessageService.get_unread_count(user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'unread_count': result['total'],
            'direct': result['direct'],
            'groups': result['groups']
        }), 200
        
    except Exception as e:
        logger.error(f"Get unread count error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get unread count'}), 500

@messages_bp.route('/unread-by-chat', methods=['GET'])
@jwt_required()
def get_unread_count_by_chat():
    """
    Get unread message counts broken down per conversation, for a chat-list
    badge shown before a chat is opened.
    ---
    tags:
      - Messages
    responses:
      200:
        description: Per-chat unread counts retrieved
    """
    try:
        user_id = int(get_jwt_identity())

        result = MessageService.get_unread_count_by_chat(user_id)

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Get unread count by chat error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get unread count by chat'}), 500

@messages_bp.route('/<int:message_id>/read', methods=['POST'])
@jwt_required()
def mark_as_read(message_id):
    """
    Mark a message as read
    ---
    tags:
      - Messages
    parameters:
      - name: message_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Message marked as read
    """
    try:
        user_id = int(get_jwt_identity())
        
        message = Message.query.get(message_id)
        if not message:
            return jsonify({'error': 'Message not found'}), 404
        
        # Check if user has access
        if message.recipient_type == 'user':
            if message.recipient_id != user_id and message.sender_id != user_id:
                return jsonify({'error': 'Unauthorized'}), 403
        elif message.recipient_type == 'group':
            from services.group_service import GroupService
            if not GroupService.is_member(user_id, message.recipient_id):
                return jsonify({'error': 'Unauthorized'}), 403
        
        # Mark as read
        message.mark_as_read(user_id)
        
        return jsonify({'message': 'Message marked as read'}), 200
        
    except Exception as e:
        logger.error(f"Mark as read error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to mark message as read'}), 500

# Debug endpoint for testing
@messages_bp.route('/debug', methods=['GET'])
@jwt_required()
def debug_messages():
    """Debug endpoint to check messages table"""
    try:
        user_id = int(get_jwt_identity())
        
        # Check messages table
        from sqlalchemy import text
        result = db.session.execute(text("SHOW TABLES LIKE 'messages'"))
        table_exists = result.rowcount > 0
        
        if not table_exists:
            return jsonify({'error': 'Messages table does not exist'}), 500
        
        # Get message count
        count = Message.query.count()
        
        # Get sample messages
        messages = Message.query.limit(5).all()
        
        return jsonify({
            'table_exists': table_exists,
            'message_count': count,
            'user_id': user_id,
            'sample_messages': [{
                'id': m.id,
                'sender_id': m.sender_id,
                'recipient_id': m.recipient_id,
                'recipient_type': m.recipient_type,
                'created_at': m.created_at.isoformat()
            } for m in messages]
        }), 200
        
    except Exception as e:
        logger.error(f"Debug error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500