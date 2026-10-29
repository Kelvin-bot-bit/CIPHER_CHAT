# backend/routes/users.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User, FriendRequest
from services.user_service import UserService
from services.friend_service import FriendService
from extensions import db
import logging

users_bp = Blueprint('users', __name__)
logger = logging.getLogger(__name__)

@users_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get current user's profile"""
    try:
        user_id = int(get_jwt_identity())
        result = UserService.get_user_profile(user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 404
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get profile'}), 500

@users_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        result = UserService.update_profile(
            user_id=user_id,
            full_name=data.get('full_name'),
            bio=data.get('bio'),
            profile_picture=data.get('profile_picture')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': result['user']
        }), 200
        
    except Exception as e:
        logger.error(f"Update profile error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to update profile'}), 500

@users_bp.route('/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user(user_id):
    """Get user by ID"""
    try:
        current_user_id = int(get_jwt_identity())
        
        result = UserService.get_user_profile(user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 404
        
        user_data = result['profile']
        
        # Add relationship info
        if current_user_id != user_id:
            user_data['is_friend'] = FriendService.are_friends(current_user_id, user_id)
            user_data['is_blocked'] = FriendService.is_blocked(current_user_id, user_id)
            user_data['has_pending_request'] = FriendRequest.has_pending_request(
                current_user_id, user_id
            )
        
        return jsonify({'user': user_data}), 200
        
    except Exception as e:
        logger.error(f"Get user error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get user'}), 500

@users_bp.route('/search', methods=['GET'])
@jwt_required()
def search_users():
    """Search for users"""
    try:
        user_id = int(get_jwt_identity())
        query = request.args.get('query')
        
        if not query or len(query) < 2:
            return jsonify({
                'error': 'Search query must be at least 2 characters'
            }), 400
        
        result = UserService.search_users(query, user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Search users error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to search users'}), 500

@users_bp.route('/status', methods=['PUT'])
@jwt_required()
def update_online_status():
    """Update user's online status"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('status'):
            return jsonify({'error': 'Status is required'}), 400
        
        result = UserService.update_online_status(user_id, data['status'])
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Status updated successfully',
            'status': result['status'],
            'last_seen': result['last_seen']
        }), 200
        
    except Exception as e:
        logger.error(f"Update status error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to update status'}), 500

@users_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_user_stats():
    """Get user statistics"""
    try:
        user_id = int(get_jwt_identity())
        
        logger.info(f"Getting stats for user_id: {user_id}")
        
        # Get user stats
        result = UserService.get_user_stats(user_id)
        
        if result.get('error'):
            logger.error(f"Stats error: {result['error']}")
            return jsonify({'error': result['error']}), 400
        
        logger.info(f"Stats retrieved successfully")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get user stats error: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'Failed to get user stats: {str(e)}'
        }), 500

@users_bp.route('/online', methods=['GET'])
@jwt_required()
def get_online_users():
    """Get online users"""
    try:
        user_id = int(get_jwt_identity())
        
        result = UserService.get_online_users(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get online users error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get online users'}), 500

@users_bp.route('/recent', methods=['GET'])
@jwt_required()
def get_recent_users():
    """Get recent users"""
    try:
        user_id = int(get_jwt_identity())
        limit = request.args.get('limit', 10, type=int)
        
        result = UserService.get_recent_users(user_id, limit)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get recent users error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get recent users'}), 500

@users_bp.route('/contacts', methods=['GET'])
@jwt_required()
def get_contacts():
    """Get user contacts (friends and groups)"""
    try:
        user_id = int(get_jwt_identity())
        
        result = UserService.get_user_contacts(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get contacts error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get contacts'}), 500

@users_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user info (alias for profile)"""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': user.to_dict(include_private=True)
        }), 200
        
    except Exception as e:
        logger.error(f"Get current user error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get user'}), 500