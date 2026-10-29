# backend/services/friend_service.py
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import or_, and_
from models import Friend, FriendRequest, BlockedUser, User, Notification
from extensions import db
from .notification_service import NotificationService

class FriendService:
    """Handles all friend-related operations"""
    
    @staticmethod
    def send_friend_request(sender_id: int, receiver_id: int, message: str = None) -> dict:
        """
        Send a friend request
        
        Args:
            sender_id: ID of user sending the request
            receiver_id: ID of user receiving the request
            message: Optional message with the request
        
        Returns:
            Dictionary with success or error
        """
        # Validate users
        sender = User.query.get(sender_id)
        receiver = User.query.get(receiver_id)
        
        if not sender or not receiver:
            return {'error': 'User not found'}
        
        if sender_id == receiver_id:
            return {'error': 'You cannot send a friend request to yourself'}
        
        # Check if already friends
        if FriendService.are_friends(sender_id, receiver_id):
            return {'error': 'You are already friends'}
        
        # Check if there's a pending request
        existing = FriendRequest.query.filter(
            or_(
                and_(
                    FriendRequest.sender_id == sender_id,
                    FriendRequest.receiver_id == receiver_id,
                    FriendRequest.status == 'pending'
                ),
                and_(
                    FriendRequest.sender_id == receiver_id,
                    FriendRequest.receiver_id == sender_id,
                    FriendRequest.status == 'pending'
                )
            )
        ).first()
        
        if existing:
            return {'error': 'A friend request is already pending'}
        
        # Check if blocked
        if FriendService.is_blocked(sender_id, receiver_id):
            return {'error': 'You have blocked this user'}
        
        if FriendService.is_blocked(receiver_id, sender_id):
            return {'error': 'This user has blocked you'}
        
        try:
            # Create friend request
            friend_request = FriendRequest(
                sender_id=sender_id,
                receiver_id=receiver_id,
                message=message,
                status='pending'
            )
            db.session.add(friend_request)
            db.session.commit()
            
            # Create notification
            NotificationService.create_notification(
                user_id=receiver_id,
                notification_type='friend_request',
                sender_id=sender_id,
                message=f'{sender.username} sent you a friend request',
                reference_id=friend_request.id
            )
            
            return {
                'success': True,
                'request_id': friend_request.id,
                'request': friend_request.to_dict()
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to send friend request: {str(e)}'}
    
    @staticmethod
    def accept_friend_request(request_id: int, user_id: int) -> dict:
        """
        Accept a friend request
        
        Args:
            request_id: ID of the friend request
            user_id: ID of the user accepting
        
        Returns:
            Dictionary with success or error
        """
        friend_request = FriendRequest.query.get(request_id)
        if not friend_request:
            return {'error': 'Friend request not found'}
        
        # Check if user is the receiver
        if friend_request.receiver_id != user_id:
            return {'error': 'You cannot accept this request'}
        
        if friend_request.status != 'pending':
            return {'error': 'This request is no longer pending'}
        
        try:
            # Accept the request
            friend_request.accept()
            
            # Create notifications.
            # `user_id` here is the accepter's id, not a username — the
            # message previously interpolated the raw numeric id, so a
            # notification would read "5 accepted your friend request"
            # instead of a name. Look the accepter up so it reads properly.
            accepter = User.query.get(user_id)
            accepter_label = accepter.username if accepter else 'Someone'
            NotificationService.create_notification(
                user_id=friend_request.sender_id,
                notification_type='friend_request',
                sender_id=user_id,
                message=f'{accepter_label} accepted your friend request',
                reference_id=request_id
            )
            
            return {
                'success': True,
                'friendship': {
                    'user1_id': friend_request.sender_id,
                    'user2_id': friend_request.receiver_id
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to accept friend request: {str(e)}'}
    
    @staticmethod
    def reject_friend_request(request_id: int, user_id: int) -> dict:
        """
        Reject a friend request
        
        Args:
            request_id: ID of the friend request
            user_id: ID of the user rejecting
        
        Returns:
            Dictionary with success or error
        """
        friend_request = FriendRequest.query.get(request_id)
        if not friend_request:
            return {'error': 'Friend request not found'}
        
        if friend_request.receiver_id != user_id:
            return {'error': 'You cannot reject this request'}
        
        if friend_request.status != 'pending':
            return {'error': 'This request is no longer pending'}
        
        try:
            friend_request.reject()
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to reject friend request: {str(e)}'}
    
    @staticmethod
    def cancel_friend_request(request_id: int, user_id: int) -> dict:
        """
        Cancel a friend request
        
        Args:
            request_id: ID of the friend request
            user_id: ID of the user cancelling
        
        Returns:
            Dictionary with success or error
        """
        friend_request = FriendRequest.query.get(request_id)
        if not friend_request:
            return {'error': 'Friend request not found'}
        
        if friend_request.sender_id != user_id:
            return {'error': 'You cannot cancel this request'}
        
        if friend_request.status != 'pending':
            return {'error': 'This request is no longer pending'}
        
        try:
            friend_request.cancel()
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to cancel friend request: {str(e)}'}
    
    @staticmethod
    def remove_friend(user_id: int, friend_id: int) -> dict:
        """
        Remove a friend
        
        Args:
            user_id: ID of the user removing
            friend_id: ID of the friend to remove
        
        Returns:
            Dictionary with success or error
        """
        if not FriendService.are_friends(user_id, friend_id):
            return {'error': 'You are not friends'}
        
        try:
            # Remove friendship entries
            friendship1 = Friend.query.filter_by(
                user_id=user_id,
                friend_id=friend_id
            ).first()
            
            friendship2 = Friend.query.filter_by(
                user_id=friend_id,
                friend_id=user_id
            ).first()
            
            if friendship1:
                db.session.delete(friendship1)
            if friendship2:
                db.session.delete(friendship2)
            
            db.session.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to remove friend: {str(e)}'}
    
    @staticmethod
    def block_user(user_id: int, block_id: int, reason: str = None) -> dict:
        """
        Block a user
        
        Args:
            user_id: ID of the user blocking
            block_id: ID of the user to block
            reason: Reason for blocking
        
        Returns:
            Dictionary with success or error
        """
        if user_id == block_id:
            return {'error': 'You cannot block yourself'}
        
        # Check if already blocked
        if FriendService.is_blocked(user_id, block_id):
            return {'error': 'User is already blocked'}
        
        try:
            # Create block entry
            block = BlockedUser(
                blocker_id=user_id,
                blocked_id=block_id,
                reason=reason
            )
            db.session.add(block)
            
            # Remove friendship if exists
            if FriendService.are_friends(user_id, block_id):
                FriendService.remove_friend(user_id, block_id)
            
            # Also block in friends table
            friendship = Friend.query.filter_by(
                user_id=user_id,
                friend_id=block_id
            ).first()
            if friendship:
                friendship.is_blocked = True
                friendship.blocked_by = user_id
            
            db.session.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to block user: {str(e)}'}
    
    @staticmethod
    def unblock_user(user_id: int, block_id: int) -> dict:
        """
        Unblock a user
        
        Args:
            user_id: ID of the user unblocking
            block_id: ID of the user to unblock
        
        Returns:
            Dictionary with success or error
        """
        block = BlockedUser.query.filter_by(
            blocker_id=user_id,
            blocked_id=block_id
        ).first()
        
        if not block:
            return {'error': 'User is not blocked'}
        
        try:
            db.session.delete(block)
            
            # Unblock in friends table
            friendship = Friend.query.filter_by(
                user_id=user_id,
                friend_id=block_id
            ).first()
            if friendship:
                friendship.is_blocked = False
                friendship.blocked_by = None
            
            db.session.commit()
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to unblock user: {str(e)}'}
    
    @staticmethod
    def get_friends(user_id: int) -> dict:
        """
        Get all friends of a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with friends list
        """
        friends = User.query.join(
            Friend, or_(
                Friend.user_id == User.id,
                Friend.friend_id == User.id
            )
        ).filter(
            or_(
                Friend.user_id == user_id,
                Friend.friend_id == user_id
            ),
            Friend.is_blocked == False,
            User.id != user_id
        ).all()
        
        return {
            'success': True,
            'friends': [friend.to_dict() for friend in friends],
            'total': len(friends)
        }
    
    @staticmethod
    def get_friend_requests(user_id: int) -> dict:
        """
        Get all friend requests for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with friend requests
        """
        # Get received requests
        received = FriendRequest.query.filter_by(
            receiver_id=user_id,
            status='pending'
        ).order_by(FriendRequest.created_at.desc()).all()
        
        # Get sent requests
        sent = FriendRequest.query.filter_by(
            sender_id=user_id,
            status='pending'
        ).order_by(FriendRequest.created_at.desc()).all()
        
        return {
            'success': True,
            'received': [req.to_dict() for req in received],
            'sent': [req.to_dict() for req in sent],
            'total_received': len(received),
            'total_sent': len(sent)
        }
    
    @staticmethod
    def get_blocked_users(user_id: int) -> dict:
        """
        Get all blocked users for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with blocked users
        """
        blocks = BlockedUser.query.filter_by(blocker_id=user_id).all()
        blocked_users = []
        
        for block in blocks:
            user = User.query.get(block.blocked_id)
            if user:
                blocked_users.append({
                    'user': user.to_dict(),
                    'reason': block.reason,
                    'blocked_at': block.created_at.isoformat()
                })
        
        return {
            'success': True,
            'blocked_users': blocked_users,
            'total': len(blocked_users)
        }
    
    @staticmethod
    def search_users(query: str, user_id: int = None) -> dict:
        """
        Search for users
        
        Args:
            query: Search query
            user_id: Current user ID (to exclude from results)
        
        Returns:
            Dictionary with search results
        """
        search = f"%{query}%"
        users = User.query.filter(
            or_(
                User.username.ilike(search),
                User.full_name.ilike(search),
                User.email.ilike(search)
            ),
            User.is_active == True,
            User.is_suspended == False
        )
        
        if user_id:
            users = users.filter(User.id != user_id)
        
        users = users.limit(20).all()
        
        results = []
        for user in users:
            user_dict = user.to_dict()
            if user_id:
                user_dict['is_friend'] = FriendService.are_friends(user_id, user.id)
                user_dict['has_pending_request'] = FriendRequest.has_pending_request(user_id, user.id)
                user_dict['is_blocked'] = FriendService.is_blocked(user_id, user.id)
            results.append(user_dict)
        
        return {
            'success': True,
            'users': results,
            'total': len(results)
        }
    
    @staticmethod
    def are_friends(user1_id: int, user2_id: int) -> bool:
        """Check if two users are friends"""
        return Friend.are_friends(user1_id, user2_id)
    
    @staticmethod
    def is_blocked(user_id: int, check_id: int) -> bool:
        """Check if a user has blocked another"""
        return BlockedUser.is_blocked(user_id, check_id)