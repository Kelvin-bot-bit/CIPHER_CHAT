# backend/socket_events/presence_events.py
from flask_socketio import emit, join_room, leave_room
from flask_jwt_extended import decode_token
from flask import request
from datetime import datetime
from models import User, Friend
from extensions import db, socketio
from socket_events.call_events import handle_user_disconnected
from socket_events.group_call_events import handle_group_call_disconnect
import logging

logger = logging.getLogger(__name__)

# Maps socket session id -> user_id for connected clients. The previous
# disconnect handler looked for this on `socketio.user_sockets`, an
# attribute nothing in this codebase ever set — so `hasattr(...)` was
# always False and disconnect never ran its body: users never got marked
# offline and friends were never notified. A plain module-level dict, kept
# in sync in connect/disconnect, is the minimal fix.
_socket_users = {}

def register_presence_events(socketio):
    """Register presence-related socket events"""
    
    @socketio.on('connect')
    def handle_connect():
        """
        Handle user connection
        ---
        Event: connect
        """
        try:
            # Get token from query string
            token = request.args.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return False
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            # Update user status
            user = User.query.get(user_id)
            if user:
                user.online_status = 'online'
                user.last_seen = datetime.utcnow()
                db.session.commit()
                
                _socket_users[request.sid] = user_id
                
                # Join user's personal room
                join_room(f"user_{user_id}")
                
                # Notify friends that user is online
                friends = Friend.query.filter_by(
                    user_id=user_id,
                    is_blocked=False
                ).all()
                
                for friend in friends:
                    emit('user_online', {
                        'user_id': user_id,
                        'username': user.username,
                        'timestamp': datetime.utcnow().isoformat()
                    }, room=f"user_{friend.friend_id}")
                
                logger.info(f"User {user_id} connected")
                return True
            
        except Exception as e:
            logger.error(f"Connect error: {str(e)}")
            return False
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """
        Handle user disconnection
        ---
        Event: disconnect
        """
        try:
            user_id = _socket_users.pop(request.sid, None)

            # End any live call this socket was part of, so the other people
            # are told straight away and the user isn't left marked "busy".
            # (handle_user_disconnected was written for exactly this but was
            # never actually called from anywhere.) Group calls are tied to
            # the exact socket that joined; 1:1 calls are per user, so they
            # only end once the user has no connected sockets left.
            if user_id:
                try:
                    handle_group_call_disconnect(user_id, request.sid)
                    if user_id not in _socket_users.values():
                        handle_user_disconnected(user_id)
                except Exception as e:
                    logger.error(f"Call cleanup on disconnect failed: {str(e)}")

            if user_id:
                # Update user status
                user = User.query.get(user_id)
                if user:
                    user.online_status = 'offline'
                    user.last_seen = datetime.utcnow()
                    db.session.commit()
                    
                    # Notify friends that user is offline
                    friends = Friend.query.filter_by(
                        user_id=user_id,
                        is_blocked=False
                    ).all()
                    
                    for friend in friends:
                        emit('user_offline', {
                            'user_id': user_id,
                            'username': user.username,
                            'last_seen': user.last_seen.isoformat(),
                            'timestamp': datetime.utcnow().isoformat()
                        }, room=f"user_{friend.friend_id}")
                    
                    # Leave user's room
                    leave_room(f"user_{user_id}")
                    
                    logger.info(f"User {user_id} disconnected")
            
        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")
    
    @socketio.on('update_status')
    def handle_update_status(data):
        """
        Update user's online status
        ---
        Event: update_status
        Data: {
            'status': 'online' | 'away' | 'busy' | 'offline',
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
            
            status = data.get('status')
            if not status or status not in ['online', 'away', 'busy', 'offline']:
                emit('error', {'message': 'Invalid status'})
                return
            
            user = User.query.get(user_id)
            if not user:
                emit('error', {'message': 'User not found'})
                return
            
            # Update status
            user.online_status = status
            if status == 'offline':
                user.last_seen = datetime.utcnow()
            db.session.commit()
            
            # Notify friends
            friends = Friend.query.filter_by(
                user_id=user_id,
                is_blocked=False
            ).all()
            
            for friend in friends:
                emit('status_updated', {
                    'user_id': user_id,
                    'status': status,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=f"user_{friend.friend_id}")
            
            # Acknowledge update
            emit('status_updated_ack', {
                'status': status,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            logger.info(f"User {user_id} updated status to {status}")
            
        except Exception as e:
            logger.error(f"Update status error: {str(e)}")
            emit('error', {'message': 'Failed to update status'})
    
    @socketio.on('get_online_friends')
    def handle_get_online_friends(data):
        """
        Get online friends
        ---
        Event: get_online_friends
        Data: {
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
            
            # Get friends
            friends = Friend.query.filter_by(
                user_id=user_id,
                is_blocked=False
            ).all()
            
            online_friends = []
            for friend in friends:
                friend_user = User.query.get(friend.friend_id)
                if friend_user and friend_user.online_status != 'offline':
                    online_friends.append({
                        'user_id': friend_user.id,
                        'username': friend_user.username,
                        'full_name': friend_user.full_name,
                        'status': friend_user.online_status,
                        'last_seen': friend_user.last_seen.isoformat()
                    })
            
            emit('online_friends', {
                'friends': online_friends,
                'count': len(online_friends),
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Get online friends error: {str(e)}")
            emit('error', {'message': 'Failed to get online friends'})
    
    @socketio.on('ping')
    def handle_ping(data):
        """
        Handle ping to keep connection alive
        ---
        Event: ping
        """
        try:
            token = data.get('token')
            if not token:
                emit('error', {'message': 'Authentication required'})
                return
            
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
            
            # Update last seen
            user = User.query.get(user_id)
            if user:
                user.last_seen = datetime.utcnow()
                db.session.commit()
            
            emit('pong', {
                'timestamp': datetime.utcnow().isoformat(),
                'user_id': user_id
            })
            
        except Exception as e:
            logger.error(f"Ping error: {str(e)}")
            emit('error', {'message': 'Failed to process ping'})