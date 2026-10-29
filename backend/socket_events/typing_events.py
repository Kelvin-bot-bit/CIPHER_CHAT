# backend/socket_events/typing_events.py
from flask_socketio import emit, join_room, leave_room
from flask_jwt_extended import decode_token
from flask import request
from datetime import datetime
from models import User, Group, GroupMember
from extensions import db, socketio
import logging

logger = logging.getLogger(__name__)

def register_typing_events(socketio):
    """Register typing-related socket events"""
    
    @socketio.on('typing_start')
    def handle_typing_start(data):
        """
        User started typing
        ---
        Event: typing_start
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
                emit('error', {'message': 'Chat ID and type required'})
                return
            
            # Verify user has access to the chat
            has_access = False
            
            if chat_type == 'user':
                # Check if users are friends
                from services.friend_service import FriendService
                has_access = FriendService.are_friends(user_id, chat_id)
            elif chat_type == 'group':
                # Check if user is a member of the group
                group = Group.query.get(chat_id)
                if group:
                    has_access = group.is_member(user_id)
            
            if not has_access:
                emit('error', {'message': 'Unauthorized'})
                return
            
            # Get user info for display
            user = User.query.get(user_id)
            
            # Emit typing event to room
            room = f"{chat_type}_{chat_id}"
            emit('user_typing', {
                'user_id': user_id,
                'username': user.username,
                'chat_id': chat_id,
                'chat_type': chat_type,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room, include_self=False)
            
            logger.debug(f"User {user_id} started typing in {chat_type}_{chat_id}")
            
        except Exception as e:
            logger.error(f"Typing start error: {str(e)}")
            emit('error', {'message': 'Failed to register typing'})
    
    @socketio.on('typing_stop')
    def handle_typing_stop(data):
        """
        User stopped typing
        ---
        Event: typing_stop
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
                emit('error', {'message': 'Chat ID and type required'})
                return
            
            # Emit typing stopped event to room
            room = f"{chat_type}_{chat_id}"
            emit('user_stopped_typing', {
                'user_id': user_id,
                'chat_id': chat_id,
                'chat_type': chat_type,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room, include_self=False)
            
            logger.debug(f"User {user_id} stopped typing in {chat_type}_{chat_id}")
            
        except Exception as e:
            logger.error(f"Typing stop error: {str(e)}")
            emit('error', {'message': 'Failed to stop typing'})