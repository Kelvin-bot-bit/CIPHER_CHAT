# backend/routes/friends.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.friend_service import FriendService
from services.notification_service import NotificationService
from models import User
from extensions import db
import logging

friends_bp = Blueprint('friends', __name__)
logger = logging.getLogger(__name__)

@friends_bp.route('/request', methods=['POST'])
@jwt_required()
def send_friend_request():
    """
    Send a friend request
    ---
    tags:
      - Friends
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - user_id
          properties:
            user_id:
              type: integer
            message:
              type: string
    responses:
      200:
        description: Friend request sent
      400:
        description: Validation error
    """
    try:
        sender_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('user_id'):
            return jsonify({'error': 'User ID is required'}), 400
        
        result = FriendService.send_friend_request(
            sender_id=sender_id,
            receiver_id=data['user_id'],
            message=data.get('message')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Friend request sent successfully',
            'request_id': result['request_id']
        }), 200
        
    except Exception as e:
        logger.error(f"Send friend request error: {str(e)}")
        return jsonify({'error': 'Failed to send friend request'}), 500

@friends_bp.route('/request/<int:request_id>/accept', methods=['POST'])
@jwt_required()
def accept_friend_request(request_id):
    """
    Accept a friend request
    ---
    tags:
      - Friends
    parameters:
      - name: request_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Friend request accepted
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.accept_friend_request(request_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Friend request accepted',
            'friendship': result.get('friendship')
        }), 200
        
    except Exception as e:
        logger.error(f"Accept friend request error: {str(e)}")
        return jsonify({'error': 'Failed to accept friend request'}), 500

@friends_bp.route('/request/<int:request_id>/reject', methods=['POST'])
@jwt_required()
def reject_friend_request(request_id):
    """
    Reject a friend request
    ---
    tags:
      - Friends
    parameters:
      - name: request_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Friend request rejected
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.reject_friend_request(request_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Friend request rejected'}), 200
        
    except Exception as e:
        logger.error(f"Reject friend request error: {str(e)}")
        return jsonify({'error': 'Failed to reject friend request'}), 500

@friends_bp.route('/request/<int:request_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_friend_request(request_id):
    """
    Cancel a friend request
    ---
    tags:
      - Friends
    parameters:
      - name: request_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Friend request cancelled
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.cancel_friend_request(request_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Friend request cancelled'}), 200
        
    except Exception as e:
        logger.error(f"Cancel friend request error: {str(e)}")
        return jsonify({'error': 'Failed to cancel friend request'}), 500

@friends_bp.route('/<int:friend_id>', methods=['DELETE'])
@jwt_required()
def remove_friend(friend_id):
    """
    Remove a friend
    ---
    tags:
      - Friends
    parameters:
      - name: friend_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Friend removed
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.remove_friend(user_id, friend_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Friend removed successfully'}), 200
        
    except Exception as e:
        logger.error(f"Remove friend error: {str(e)}")
        return jsonify({'error': 'Failed to remove friend'}), 500

@friends_bp.route('/block', methods=['POST'])
@jwt_required()
def block_user():
    """
    Block a user
    ---
    tags:
      - Friends
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - user_id
          properties:
            user_id:
              type: integer
            reason:
              type: string
    responses:
      200:
        description: User blocked
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('user_id'):
            return jsonify({'error': 'User ID is required'}), 400
        
        result = FriendService.block_user(
            user_id=user_id,
            block_id=data['user_id'],
            reason=data.get('reason')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'User blocked successfully'}), 200
        
    except Exception as e:
        logger.error(f"Block user error: {str(e)}")
        return jsonify({'error': 'Failed to block user'}), 500

@friends_bp.route('/unblock', methods=['POST'])
@jwt_required()
def unblock_user():
    """
    Unblock a user
    ---
    tags:
      - Friends
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - user_id
          properties:
            user_id:
              type: integer
    responses:
      200:
        description: User unblocked
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('user_id'):
            return jsonify({'error': 'User ID is required'}), 400
        
        result = FriendService.unblock_user(user_id, data['user_id'])
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'User unblocked successfully'}), 200
        
    except Exception as e:
        logger.error(f"Unblock user error: {str(e)}")
        return jsonify({'error': 'Failed to unblock user'}), 500

@friends_bp.route('/list', methods=['GET'])
@jwt_required()
def get_friends():
    """
    Get list of friends
    ---
    tags:
      - Friends
    responses:
      200:
        description: Friends list retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.get_friends(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get friends error: {str(e)}")
        return jsonify({'error': 'Failed to get friends'}), 500

@friends_bp.route('/requests', methods=['GET'])
@jwt_required()
def get_friend_requests():
    """
    Get friend requests
    ---
    tags:
      - Friends
    responses:
      200:
        description: Friend requests retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.get_friend_requests(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get friend requests error: {str(e)}")
        return jsonify({'error': 'Failed to get friend requests'}), 500

@friends_bp.route('/blocked', methods=['GET'])
@jwt_required()
def get_blocked_users():
    """
    Get blocked users
    ---
    tags:
      - Friends
    responses:
      200:
        description: Blocked users retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FriendService.get_blocked_users(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get blocked users error: {str(e)}")
        return jsonify({'error': 'Failed to get blocked users'}), 500

@friends_bp.route('/search', methods=['GET'])
@jwt_required()
def search_users():
    """
    Search for users
    ---
    tags:
      - Friends
    parameters:
      - name: query
        in: query
        required: true
        type: string
    responses:
      200:
        description: Search results
    """
    try:
        user_id = int(get_jwt_identity())
        query = request.args.get('query')
        
        if not query or len(query) < 2:
            return jsonify({'error': 'Search query must be at least 2 characters'}), 400
        
        result = FriendService.search_users(query, user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Search users error: {str(e)}")
        return jsonify({'error': 'Failed to search users'}), 500