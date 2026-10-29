# backend/routes/notifications.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.notification_service import NotificationService
import logging

notifications_bp = Blueprint('notifications', __name__)
logger = logging.getLogger(__name__)

@notifications_bp.route('/', methods=['GET'])
@jwt_required()
def get_notifications():
    """
    Get the current user's notifications
    ---
    tags:
      - Notifications
    parameters:
      - name: limit
        in: query
        type: integer
      - name: offset
        in: query
        type: integer
    responses:
      200:
        description: Notifications retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)

        result = NotificationService.get_user_notifications(user_id, limit=limit, offset=offset)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Get notifications error: {str(e)}")
        return jsonify({'error': 'Failed to get notifications'}), 500


@notifications_bp.route('/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """
    Get the current user's unread notification count
    ---
    tags:
      - Notifications
    responses:
      200:
        description: Unread count retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        result = NotificationService.get_unread_notification_count(user_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Get unread notification count error: {str(e)}")
        return jsonify({'error': 'Failed to get unread count'}), 500


@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@jwt_required()
def mark_as_read(notification_id):
    """
    Mark a single notification as read
    ---
    tags:
      - Notifications
    parameters:
      - name: notification_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Notification marked as read
      400:
        description: Error
    """
    try:
        user_id = int(get_jwt_identity())
        result = NotificationService.mark_notification_as_read(notification_id, user_id)

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Mark notification read error: {str(e)}")
        return jsonify({'error': 'Failed to mark notification as read'}), 500


@notifications_bp.route('/read-all', methods=['POST'])
@jwt_required()
def mark_all_as_read():
    """
    Mark all of the current user's notifications as read
    ---
    tags:
      - Notifications
    responses:
      200:
        description: All notifications marked as read
    """
    try:
        user_id = int(get_jwt_identity())
        result = NotificationService.mark_all_notifications_as_read(user_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Mark all notifications read error: {str(e)}")
        return jsonify({'error': 'Failed to mark notifications as read'}), 500


@notifications_bp.route('/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """
    Delete a notification
    ---
    tags:
      - Notifications
    parameters:
      - name: notification_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Notification deleted
      400:
        description: Error
    """
    try:
        user_id = int(get_jwt_identity())
        result = NotificationService.delete_notification(notification_id, user_id)

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Delete notification error: {str(e)}")
        return jsonify({'error': 'Failed to delete notification'}), 500