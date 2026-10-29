# backend/services/user_service.py - Complete Fixed Version
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import or_, text
from sqlalchemy.exc import SQLAlchemyError
from models import User, Friend, FriendRequest, BlockedUser, Message
from extensions import db
from services.friend_service import FriendService

class UserService:
    """Handles all user-related operations"""
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[User]:
        """Get user by ID"""
        return User.query.get(user_id)
    
    @staticmethod
    def get_user_by_username(username: str) -> Optional[User]:
        """Get user by username"""
        return User.query.filter_by(username=username.lower()).first()
    
    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """Get user by email"""
        return User.query.filter_by(email=email.lower()).first()
    
    @staticmethod
    def search_users(query: str, current_user_id: int = None) -> dict:
        """
        Search for users by username, full name, or email
        
        Args:
            query: Search query
            current_user_id: ID of the current user (to exclude from results)
        
        Returns:
            Dictionary with search results
        """
        if not query or len(query.strip()) < 2:
            return {
                'success': True,
                'users': [],
                'total': 0,
                'message': 'Search query must be at least 2 characters'
            }
        
        search = f"%{query.strip()}%"
        users_query = User.query.filter(
            or_(
                User.username.ilike(search),
                User.full_name.ilike(search),
                User.email.ilike(search)
            ),
            User.is_active == True,
            User.is_suspended == False
        )
        
        if current_user_id:
            users_query = users_query.filter(User.id != current_user_id)
        
        users = users_query.limit(50).all()
        
        results = []
        for user in users:
            user_dict = user.to_dict()
            
            if current_user_id:
                # Add relationship info
                user_dict['is_friend'] = FriendService.are_friends(current_user_id, user.id)
                user_dict['is_blocked'] = FriendService.is_blocked(current_user_id, user.id)
                user_dict['has_pending_request'] = FriendRequest.has_pending_request(
                    current_user_id, user.id
                )
                user_dict['friend_request_status'] = UserService._get_friend_request_status(
                    current_user_id, user.id
                )
            
            results.append(user_dict)
        
        return {
            'success': True,
            'users': results,
            'total': len(results)
        }
    
    @staticmethod
    def _get_friend_request_status(user_id: int, other_id: int) -> Optional[str]:
        """Get the status of a friend request between two users"""
        request = FriendRequest.query.filter(
            or_(
                (FriendRequest.sender_id == user_id) & (FriendRequest.receiver_id == other_id),
                (FriendRequest.sender_id == other_id) & (FriendRequest.receiver_id == user_id)
            )
        ).first()
        
        if request:
            return request.status
        return None
    
    @staticmethod
    def update_online_status(user_id: int, status: str) -> dict:
        """
        Update user's online status
        
        Args:
            user_id: User ID
            status: New status ('online', 'offline', 'away', 'busy')
        
        Returns:
            Dictionary with success or error
        """
        valid_statuses = ['online', 'offline', 'away', 'busy']
        if status not in valid_statuses:
            return {'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}
        
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        user.online_status = status
        if status == 'offline':
            user.last_seen = datetime.utcnow()
        
        db.session.commit()
        
        return {
            'success': True,
            'status': status,
            'last_seen': user.last_seen.isoformat() if user.last_seen else None
        }
    
    @staticmethod
    def update_profile(
        user_id: int,
        full_name: str = None,
        bio: str = None,
        profile_picture: str = None
    ) -> dict:
        """
        Update user profile
        
        Args:
            user_id: User ID
            full_name: User's full name
            bio: User's bio
            profile_picture: Profile picture URL/path
        
        Returns:
            Dictionary with success or error
        """
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        if full_name is not None:
            user.full_name = full_name
        
        if bio is not None:
            user.bio = bio
        
        if profile_picture is not None:
            user.profile_picture = profile_picture
        
        db.session.commit()
        
        return {
            'success': True,
            'user': user.to_dict(include_private=True)
        }
    
    @staticmethod
    def get_user_profile(user_id: int) -> dict:
        """
        Get user profile with additional info
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with user profile
        """
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        # Get additional stats
        friend_count = user.friends_as_user.filter_by(is_blocked=False).count()
        group_count = user.group_memberships.filter_by(is_active=True).count()
        
        profile = user.to_dict(include_private=True, include_keys=True)
        profile.update({
            'friend_count': friend_count,
            'group_count': group_count,
            'unread_count': user.get_unread_count(),
            'is_online': user.is_online,
            'last_online': user.last_online
        })
        
        return {
            'success': True,
            'profile': profile
        }
    
    @staticmethod
    def get_user_stats(user_id: int) -> dict:
        """
        Get user statistics with safe error handling
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with user statistics
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return {'error': 'User not found'}
            
            # Safely count messages with error handling
            total_messages = 0
            try:
                total_messages = db.session.query(Message).filter(Message.sender_id == user_id).count()
            except SQLAlchemyError as e:
                print(f"Error counting messages: {e}")
                total_messages = 0
            
            # Safely get unread count
            unread_messages = 0
            try:
                unread_messages = user.get_unread_count() if hasattr(user, 'get_unread_count') else 0
            except SQLAlchemyError as e:
                print(f"Error getting unread count: {e}")
                unread_messages = 0
            
            # Safely count friends
            friend_count = 0
            try:
                friend_count = user.friends_as_user.filter_by(is_blocked=False).count()
            except SQLAlchemyError as e:
                print(f"Error counting friends: {e}")
                friend_count = 0
            
            # Safely count groups
            group_count = 0
            try:
                group_count = user.group_memberships.filter_by(is_active=True).count()
            except SQLAlchemyError as e:
                print(f"Error counting groups: {e}")
                group_count = 0
            
            # Safely count pending requests
            pending_requests = 0
            try:
                pending_requests = user.friend_requests_received.filter_by(status='pending').count()
            except SQLAlchemyError as e:
                print(f"Error counting pending requests: {e}")
                pending_requests = 0
            
            return {
                'success': True,
                'stats': {
                    'total_messages_sent': total_messages,
                    'unread_messages': unread_messages,
                    'friend_count': friend_count,
                    'pending_friend_requests': pending_requests,
                    'group_count': group_count,
                    'account_created': user.created_at.isoformat() if user.created_at else None,
                    'last_active': user.last_seen.isoformat() if user.last_seen else None,
                    'is_verified': user.is_verified,
                    'is_admin': user.is_admin,
                    'is_suspended': user.is_suspended,
                    'is_active': user.is_active
                }
            }
        except Exception as e:
            print(f"Unexpected error in get_user_stats: {e}")
            # Return basic stats on error
            return {
                'success': True,
                'stats': {
                    'user_id': user_id,
                    'total_messages_sent': 0,
                    'unread_messages': 0,
                    'friend_count': 0,
                    'pending_friend_requests': 0,
                    'group_count': 0,
                    'is_verified': False,
                    'is_admin': False,
                    'is_suspended': False,
                    'is_active': True
                },
                'warning': 'Some stats could not be calculated due to database error'
            }
    
    @staticmethod
    def get_online_users(user_id: int) -> dict:
        """
        Get online friends and other users
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with online users
        """
        # Get friends
        friends = Friend.query.filter_by(
            user_id=user_id,
            is_blocked=False
        ).all()
        
        friend_ids = [f.friend_id for f in friends]
        online_friends = User.query.filter(
            User.id.in_(friend_ids),
            User.online_status != 'offline',
            User.is_active == True
        ).all()
        
        # Get other online users (not friends)
        other_online = User.query.filter(
            User.id != user_id,
            User.id.notin_(friend_ids),
            User.online_status != 'offline',
            User.is_active == True,
            User.is_suspended == False
        ).limit(20).all()
        
        return {
            'success': True,
            'online_friends': [u.to_dict() for u in online_friends],
            'online_friends_count': len(online_friends),
            'other_online': [u.to_dict() for u in other_online],
            'other_online_count': len(other_online)
        }
    
    @staticmethod
    def get_recent_users(user_id: int, limit: int = 10) -> dict:
        """
        Get recently active users
        
        Args:
            user_id: User ID
            limit: Number of users to return
        
        Returns:
            Dictionary with recent users
        """
        try:
            # Get users who have recently sent messages
            recent_users = db.session.query(
                User,
                db.func.max(Message.created_at).label('last_message')
            ).join(
                Message,
                or_(
                    Message.sender_id == User.id,
                    Message.recipient_id == User.id
                )
            ).filter(
                or_(
                    Message.sender_id == user_id,
                    Message.recipient_id == user_id
                ),
                User.id != user_id,
                User.is_active == True,
                User.is_suspended == False
            ).group_by(
                User.id
            ).order_by(
                db.func.max(Message.created_at).desc()
            ).limit(limit).all()
            
            users = []
            for user, last_message in recent_users:
                user_dict = user.to_dict()
                user_dict['last_message'] = last_message.isoformat() if last_message else None
                user_dict['is_friend'] = FriendService.are_friends(user_id, user.id)
                users.append(user_dict)
            
            return {
                'success': True,
                'users': users,
                'total': len(users)
            }
        except Exception as e:
            return {
                'success': True,
                'users': [],
                'total': 0,
                'warning': f'Could not retrieve recent users: {str(e)}'
            }
    
    @staticmethod
    def get_user_contacts(user_id: int) -> dict:
        """
        Get all user contacts (friends and groups)
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with contacts
        """
        # Get friends
        friends = Friend.query.filter_by(
            user_id=user_id,
            is_blocked=False
        ).all()
        
        friend_users = []
        for friend in friends:
            user = User.query.get(friend.friend_id)
            if user and user.is_active:
                friend_users.append({
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'profile_picture': user.profile_picture,
                    'online_status': user.online_status,
                    'last_seen': user.last_seen.isoformat() if user.last_seen else None,
                    'type': 'friend',
                    'nickname': friend.nickname
                })
        
        # Get groups
        from models import Group
        groups = Group.query.join(
            GroupMember, GroupMember.group_id == Group.id
        ).filter(
            GroupMember.user_id == user_id,
            GroupMember.is_active == True,
            Group.is_active == True
        ).all()
        
        group_data = []
        for group in groups:
            group_data.append({
                'id': group.id,
                'name': group.group_name,
                'description': group.group_description,
                'picture': group.group_picture,
                'type': 'group',
                'member_count': group.get_member_count(),
                'is_admin': group.is_admin(user_id)
            })
        
        return {
            'success': True,
            'friends': friend_users,
            'friends_count': len(friend_users),
            'groups': group_data,
            'groups_count': len(group_data),
            'total_contacts': len(friend_users) + len(group_data)
        }