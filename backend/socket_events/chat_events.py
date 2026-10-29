# backend/socket_events/chat_events.py
from flask_socketio import emit, join_room, leave_room
from flask_jwt_extended import decode_token
from flask import request
from datetime import datetime
from models import User, Message, MessageStatus, Notification
from services.message_service import MessageService
from services.crypto_service import CryptoService
from services.key_management import KeyManagementService
from extensions import db, socketio
import logging

logger = logging.getLogger(__name__)

def register_chat_events(socketio):
    """Register chat-related socket events"""
    
    @socketio.on('join_chat')
    def handle_join_chat(data):
        """
        Join a chat room
        ---
        Event: join_chat
        Data: {
            'chat_id': int,
            'chat_type': 'user' | 'group',
            'token': str (JWT token)
        }
        """
        try:
            # Verify JWT token
            token = data.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            chat_id = data.get('chat_id')
            chat_type = data.get('chat_type')
            
            if not chat_id or not chat_type:
                emit('error', {'message': 'Chat ID and type are required'})
                return
            
            # Create room name
            room = f"{chat_type}_{chat_id}"
            
            # Join room
            join_room(room)
            
            # Store user's room membership
            if not hasattr(socketio, 'user_rooms'):
                socketio.user_rooms = {}
            
            if user_id not in socketio.user_rooms:
                socketio.user_rooms[user_id] = []
            
            if room not in socketio.user_rooms[user_id]:
                socketio.user_rooms[user_id].append(room)
            
            # Mark messages as delivered
            if chat_type == 'user':
                # Mark delivered for messages from this user
                messages = Message.query.filter(
                    Message.sender_id == chat_id,
                    Message.recipient_id == user_id,
                    Message.recipient_type == 'user'
                ).filter(
                    ~Message.statuses.any(
                        MessageStatus.user_id == user_id,
                        MessageStatus.status.in_(['delivered', 'read'])
                    )
                ).all()
                
                for message in messages:
                    message.mark_as_delivered(user_id)
            
            emit('joined_chat', {
                'chat_id': chat_id,
                'chat_type': chat_type,
                'user_id': user_id
            }, room=room)
            
            logger.info(f"User {user_id} joined {chat_type}_{chat_id}")
            
        except Exception as e:
            logger.error(f"Join chat error: {str(e)}")
            emit('error', {'message': 'Failed to join chat'})
    
    @socketio.on('leave_chat')
    def handle_leave_chat(data):
        """
        Leave a chat room
        ---
        Event: leave_chat
        Data: {
            'chat_id': int,
            'chat_type': 'user' | 'group',
            'token': str (JWT token)
        }
        """
        try:
            token = data.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            chat_id = data.get('chat_id')
            chat_type = data.get('chat_type')
            
            if not chat_id or not chat_type:
                emit('error', {'message': 'Chat ID and type are required'})
                return
            
            room = f"{chat_type}_{chat_id}"
            
            # Leave room
            leave_room(room)
            
            # Remove from user's rooms
            if hasattr(socketio, 'user_rooms'):
                if user_id in socketio.user_rooms:
                    if room in socketio.user_rooms[user_id]:
                        socketio.user_rooms[user_id].remove(room)
            
            emit('left_chat', {
                'chat_id': chat_id,
                'chat_type': chat_type,
                'user_id': user_id
            }, room=room)
            
            logger.info(f"User {user_id} left {chat_type}_{chat_id}")
            
        except Exception as e:
            logger.error(f"Leave chat error: {str(e)}")
            emit('error', {'message': 'Failed to leave chat'})
    
    @socketio.on('send_message')
    def handle_send_message(data):
        """
        Send a message via socket
        ---
        Event: send_message
        Data: {
            'recipient_id': int,
            'recipient_type': 'user' | 'group',
            'message': str,
            'token': str (JWT token),
            'password': str (for encryption),
            'reply_to_message_id': int (optional)
        }
        """
        try:
            # Verify JWT token
            token = data.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            recipient_id = data.get('recipient_id')
            recipient_type = data.get('recipient_type')
            plaintext = data.get('message')
            password = data.get('password')
            reply_to = data.get('reply_to_message_id')
            
            if not recipient_id or not recipient_type or not plaintext:
                emit('error', {'message': 'Missing required fields'})
                return
            
            if not password:
                emit('error', {'message': 'Password required for encryption'})
                return
            
            # Get user's private key
            private_key_result = KeyManagementService.get_user_private_key(user_id, password)
            if not private_key_result.get('success'):
                emit('error', {'message': private_key_result.get('error')})
                return
            
            sender_private_key = private_key_result['private_key']
            
            # Get recipient public key
            recipient_public_key = None
            if recipient_type == 'user':
                recipient = User.query.get(recipient_id)
                if not recipient:
                    emit('error', {'message': 'Recipient not found'})
                    return
                recipient_public_key = recipient.public_key
            
            # Send message
            result = MessageService.send_message(
                sender_id=user_id,
                recipient_id=recipient_id,
                recipient_type=recipient_type,
                plaintext=plaintext,
                sender_private_key_pem=sender_private_key,
                recipient_public_key_pem=recipient_public_key,
                reply_to_message_id=reply_to
            )
            
            if result.get('error'):
                emit('error', {'message': result['error']})
                return
            
            message = result['message']
            
            # Emit to recipient's room
            recipient_room = f"{recipient_type}_{recipient_id}"
            emit('new_message', {
                'message_id': result['message_id'],
                'sender_id': user_id,
                'recipient_id': recipient_id,
                'recipient_type': recipient_type,
                'encrypted_message': message['encrypted_message'],
                'created_at': datetime.utcnow().isoformat()
            }, room=recipient_room)
            
            # Emit delivery confirmation to sender
            emit('message_sent', {
                'message_id': result['message_id'],
                'status': 'sent',
                'timestamp': datetime.utcnow().isoformat()
            })
            
            logger.info(f"Message {result['message_id']} sent from {user_id} to {recipient_type}_{recipient_id}")
            
        except Exception as e:
            logger.error(f"Send message error: {str(e)}")
            emit('error', {'message': 'Failed to send message'})
    
    @socketio.on('message_read')
    def handle_message_read(data):
        """
        Mark message as read
        ---
        Event: message_read
        Data: {
            'message_id': int,
            'token': str (JWT token)
        }
        """
        try:
            token = data.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            message_id = data.get('message_id')
            if not message_id:
                emit('error', {'message': 'Message ID required'})
                return
            
            message = Message.query.get(message_id)
            if not message:
                emit('error', {'message': 'Message not found'})
                return
            
            # Check if user has access
            if message.recipient_type == 'user':
                if message.recipient_id != user_id and message.sender_id != user_id:
                    emit('error', {'message': 'Unauthorized'})
                    return
            elif message.recipient_type == 'group':
                from services.group_service import GroupService
                if not GroupService.is_member(user_id, message.recipient_id):
                    emit('error', {'message': 'Unauthorized'})
                    return
            
            # Mark as read
            message.mark_as_read(user_id)
            
            # Notify sender
            sender_room = f"user_{message.sender_id}"
            emit('read_receipt', {
                'message_id': message_id,
                'reader_id': user_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=sender_room)
            
            logger.info(f"Message {message_id} marked as read by {user_id}")
            
        except Exception as e:
            logger.error(f"Message read error: {str(e)}")
            emit('error', {'message': 'Failed to mark message as read'})
    
    @socketio.on('message_delivered')
    def handle_message_delivered(data):
        """
        Mark message as delivered
        ---
        Event: message_delivered
        Data: {
            'message_id': int,
            'token': str (JWT token)
        }
        """
        try:
            token = data.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            message_id = data.get('message_id')
            if not message_id:
                emit('error', {'message': 'Message ID required'})
                return
            
            message = Message.query.get(message_id)
            if not message:
                emit('error', {'message': 'Message not found'})
                return
            
            # Check if user is the recipient
            if message.recipient_type == 'user' and message.recipient_id == user_id:
                message.mark_as_delivered(user_id)
                
                # Notify sender
                sender_room = f"user_{message.sender_id}"
                emit('delivery_receipt', {
                    'message_id': message_id,
                    'delivered_to': user_id,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=sender_room)
                
                logger.info(f"Message {message_id} delivered to {user_id}")
            
        except Exception as e:
            logger.error(f"Message delivered error: {str(e)}")
            emit('error', {'message': 'Failed to mark message as delivered'})