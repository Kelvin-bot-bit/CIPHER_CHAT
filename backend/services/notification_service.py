# backend/services/notification_service.py
from datetime import datetime
from typing import List, Dict, Optional
from models import Notification, User
from extensions import db, socketio

class NotificationService:
    """Handles all notification operations"""
    
    @staticmethod
    def create_notification(
        user_id: int,
        notification_type: str,
        sender_id: int = None,
        message: str = None,
        reference_id: int = None
    ) -> Notification:
        """
        Create a new notification
        
        Args:
            user_id: ID of the user to notify
            notification_type: Type of notification
            sender_id: ID of the user who triggered the notification
            message: Notification message
            reference_id: ID of the related resource
        
        Returns:
            Created Notification object
        """
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            sender_id=sender_id,
            message=message,
            reference_id=reference_id,
            is_read=False,
            is_seen=False
        )
        db.session.add(notification)
        db.session.commit()
        
        # Send real-time notification via Socket.IO
        NotificationService.send_realtime_notification(
            user_id,
            notification.to_dict(include_sender=True)
        )
        
        # Also push it to any subscribed devices, so it reaches the user
        # even with no tab open. Import here (not at module top) to avoid
        # push_service <-> notification_service becoming a circular import
        # concern, and wrapped defensively — a push failure must never
        # break notification creation itself.
        try:
            from .push_service import PushService
            sender = User.query.get(sender_id) if sender_id else None
            title = (sender.full_name or sender.username) if sender else 'Cipher'
            PushService.send_push(
                user_id=user_id,
                title=title,
                body=message or 'You have a new notification',
                data={'notification_type': notification_type, 'reference_id': reference_id},
            )
        except Exception:
            pass
        
        return notification
    
    @staticmethod
    def send_realtime_notification(user_id: int, notification_data: dict):
        """
        Send real-time notification via Socket.IO
        
        Args:
            user_id: ID of the user to send to
            notification_data: Notification data
        """
        try:
            # This is called from plain HTTP routes (friend requests, new
            # messages, group invites), not from inside a @socketio.on
            # handler -- the bare emit() imported from flask_socketio only
            # works within an active socket event's request context, which
            # doesn't exist here, so it would silently no-op. socketio.emit()
            # (the app's actual SocketIO instance) is the documented way to
            # trigger an event from outside a socket context.
            socketio.emit('notification', notification_data, room=f'user_{user_id}')
        except Exception as e:
            # Log error but don't fail
            print(f"Failed to send real-time notification: {e}")
    
    @staticmethod
    def get_user_notifications(user_id: int, limit: int = 20, offset: int = 0) -> dict:
        """
        Get notifications for a user
        
        Args:
            user_id: User ID
            limit: Number of notifications to return
            offset: Pagination offset
        
        Returns:
            Dictionary with notifications and metadata
        """
        notifications = Notification.query.filter_by(
            user_id=user_id
        ).order_by(
            Notification.created_at.desc()
        ).limit(limit).offset(offset).all()
        
        total = Notification.query.filter_by(user_id=user_id).count()
        unread = Notification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).count()
        
        return {
            'notifications': [n.to_dict(include_sender=True) for n in notifications],
            'total': total,
            'unread': unread,
            'limit': limit,
            'offset': offset
        }
    
    @staticmethod
    def mark_notification_as_read(notification_id: int, user_id: int) -> dict:
        """
        Mark a notification as read
        
        Args:
            notification_id: Notification ID
            user_id: Current user ID
        
        Returns:
            Dictionary with success or error
        """
        notification = Notification.query.get(notification_id)
        if not notification:
            return {'error': 'Notification not found'}
        
        if notification.user_id != user_id:
            return {'error': 'You do not have permission to modify this notification'}
        
        notification.mark_as_read()
        
        return {'success': True}
    
    @staticmethod
    def mark_all_notifications_as_read(user_id: int) -> dict:
        """
        Mark all notifications as read for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with count of notifications marked as read
        """
        count = Notification.mark_all_as_read(user_id)
        
        return {
            'success': True,
            'marked_count': count
        }
    
    @staticmethod
    def delete_notification(notification_id: int, user_id: int) -> dict:
        """
        Delete a notification
        
        Args:
            notification_id: Notification ID
            user_id: Current user ID
        
        Returns:
            Dictionary with success or error
        """
        notification = Notification.query.get(notification_id)
        if not notification:
            return {'error': 'Notification not found'}
        
        if notification.user_id != user_id:
            return {'error': 'You do not have permission to delete this notification'}
        
        db.session.delete(notification)
        db.session.commit()
        
        return {'success': True}
    
    @staticmethod
    def get_unread_notification_count(user_id: int) -> dict:
        """
        Get unread notification count for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with unread count
        """
        count = Notification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).count()
        
        return {
            'unread_count': count
        }
    
    @staticmethod
    def get_notification_by_type(user_id: int, notification_type: str) -> dict:
        """
        Get notifications of a specific type
        
        Args:
            user_id: User ID
            notification_type: Type of notification
        
        Returns:
            Dictionary with notifications
        """
        notifications = Notification.query.filter_by(
            user_id=user_id,
            notification_type=notification_type
        ).order_by(
            Notification.created_at.desc()
        ).all()
        
        return {
            'notifications': [n.to_dict(include_sender=True) for n in notifications],
            'total': len(notifications)
        }