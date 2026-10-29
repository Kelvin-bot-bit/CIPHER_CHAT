# backend/services/group_service.py
from datetime import datetime
from typing import List, Dict, Optional
from models import Group, GroupMember, User, Message
from extensions import db
from .crypto_service import CryptoService
from .notification_service import NotificationService
import os

class GroupService:
    """Handles all group-related operations"""
    
    @staticmethod
    def create_group(
        creator_id: int,
        group_name: str,
        description: str = None,
        is_private: bool = False,
        member_ids: List[int] = None
    ) -> dict:
        """
        Create a new group
        
        Args:
            creator_id: ID of the group creator
            group_name: Name of the group
            description: Group description
            is_private: Whether the group is private
            member_ids: List of initial member IDs
        
        Returns:
            Dictionary with group data or error
        """
        # Validate creator
        creator = User.query.get(creator_id)
        if not creator or not creator.is_active:
            return {'error': 'User not found or inactive'}
        
        # Validate group name
        if not group_name or len(group_name) < 3:
            return {'error': 'Group name must be at least 3 characters'}
        
        # Generate group key for E2EE
        group_key = os.urandom(32)  # 256-bit AES key for group
        group_key_b64 = CryptoService.encrypt_group_key(
            group_key,
            creator.public_key
        )
        
        try:
            # Create group
            group = Group(
                group_name=group_name,
                group_description=description,
                created_by=creator_id,
                is_private=is_private,
                group_key=group_key_b64
            )
            db.session.add(group)
            db.session.commit()
            
            # Add creator as admin, with their own wrapped copy of the
            # group key (group_key_b64 was already wrapped for creator's
            # public key above).
            group.add_member(creator_id, 'admin', encrypted_group_key=group_key_b64)
            
            # Add initial members — the raw group_key bytes are still in
            # scope here (before this function returns), so each initial
            # member can get their own properly-wrapped copy directly.
            # Members added later, after this function has returned and
            # the raw key is gone, go through add_member_to_group instead,
            # which re-derives it from an existing member's copy.
            if member_ids:
                for member_id in member_ids:
                    if member_id != creator_id:
                        member_user = User.query.get(member_id)
                        if member_user and member_user.public_key:
                            member_key_b64 = CryptoService.encrypt_group_key(
                                group_key,
                                member_user.public_key
                            )
                            group.add_member(member_id, 'member', encrypted_group_key=member_key_b64)
            
            # Create notifications for added members
            if member_ids:
                for member_id in member_ids:
                    if member_id != creator_id:
                        NotificationService.create_notification(
                            user_id=member_id,
                            notification_type='group_invite',
                            sender_id=creator_id,
                            message=f'You have been added to group "{group_name}"',
                            reference_id=group.id
                        )
            
            return {
                'success': True,
                'group': group.to_dict(include_members=True)
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to create group: {str(e)}'}
    
    @staticmethod
    def add_member_to_group(
        group_id: int,
        admin_id: int,
        user_id: int,
        admin_password: str = None
    ) -> dict:
        """
        Add a member to a group
        
        Args:
            group_id: Group ID
            admin_id: ID of the user adding (must be admin)
            user_id: ID of the user to add
            admin_password: Adding admin's password — needed to unlock
                their own copy of the group key so it can be re-wrapped
                for the new member. There's no other way to get the raw
                key at this point: it only ever exists encrypted, once
                per existing member, and nobody (including the server)
                keeps a plaintext copy lying around after creation.
        
        Returns:
            Dictionary with success or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if admin has permission
        if not group.is_admin(admin_id):
            return {'error': 'Only admins can add members'}
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user or not user.is_active:
            return {'error': 'User not found or inactive'}
        
        # Check if already a member
        if group.is_member(user_id):
            return {'error': 'User is already a member'}
        
        if not admin_password:
            return {'error': 'Password required to add a member (needed to unwrap the group key)'}
        
        # Recover the raw group key via the admin's own wrapped copy, then
        # re-wrap it for the new member's public key.
        from .key_management import KeyManagementService
        admin_member = GroupMember.query.filter_by(group_id=group_id, user_id=admin_id, is_active=True).first()
        if not admin_member or not admin_member.encrypted_group_key:
            return {'error': 'Could not find your group key — try re-adding yourself as admin, or contact support'}
        
        key_result = KeyManagementService.get_user_private_key(admin_id, admin_password)
        if not key_result.get('success'):
            return {'error': key_result.get('error', 'Incorrect password')}
        
        try:
            raw_group_key = CryptoService.decrypt_group_key(
                admin_member.encrypted_group_key,
                key_result['private_key']
            )
            new_member_key_b64 = CryptoService.encrypt_group_key(raw_group_key, user.public_key)
        except Exception as e:
            return {'error': f'Failed to prepare group key for new member: {str(e)}'}
        
        try:
            # Add member
            group.add_member(user_id, 'member', encrypted_group_key=new_member_key_b64)
            
            return {
                'success': True,
                'member': {
                    'user_id': user_id,
                    'role': 'member'
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to add member: {str(e)}'}
    
    @staticmethod
    def remove_member_from_group(
        group_id: int,
        admin_id: int,
        user_id: int
    ) -> dict:
        """
        Remove a member from a group
        
        Args:
            group_id: Group ID
            admin_id: ID of the user removing (must be admin)
            user_id: ID of the user to remove
        
        Returns:
            Dictionary with success or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if admin has permission
        if not group.is_admin(admin_id):
            return {'error': 'Only admins can remove members'}
        
        # Can't remove the creator
        if group.created_by == user_id:
            return {'error': 'Cannot remove the group creator'}
        
        # Check if user is a member
        if not group.is_member(user_id):
            return {'error': 'User is not a member'}
        
        try:
            group.remove_member(user_id, admin_id)
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to remove member: {str(e)}'}
    
    @staticmethod
    def promote_to_admin(
        group_id: int,
        admin_id: int,
        user_id: int
    ) -> dict:
        """
        Promote a member to admin
        
        Args:
            group_id: Group ID
            admin_id: ID of the user promoting (must be admin)
            user_id: ID of the user to promote
        
        Returns:
            Dictionary with success or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if admin has permission
        if not group.is_admin(admin_id):
            return {'error': 'Only admins can promote members'}
        
        # Check if user is a member
        if not group.is_member(user_id):
            return {'error': 'User is not a member'}
        
        try:
            group.promote_to_admin(user_id)
            
            return {
                'success': True,
                'user_id': user_id,
                'new_role': 'admin'
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to promote member: {str(e)}'}
    
    @staticmethod
    def demote_from_admin(
        group_id: int,
        admin_id: int,
        user_id: int
    ) -> dict:
        """
        Demote an admin to member
        
        Args:
            group_id: Group ID
            admin_id: ID of the user demoting (must be admin)
            user_id: ID of the user to demote
        
        Returns:
            Dictionary with success or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if admin has permission
        if not group.is_admin(admin_id):
            return {'error': 'Only admins can demote members'}
        
        # Can't demote the creator
        if group.created_by == user_id:
            return {'error': 'Cannot demote the group creator'}
        
        # Check if user is an admin
        if not group.is_admin(user_id):
            return {'error': 'User is not an admin'}
        
        try:
            group.demote_from_admin(user_id)
            
            return {
                'success': True,
                'user_id': user_id,
                'new_role': 'member'
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to demote admin: {str(e)}'}
    
    @staticmethod
    def leave_group(
        user_id: int,
        group_id: int
    ) -> dict:
        """
        Leave a group
        
        Args:
            user_id: ID of the user leaving
            group_id: Group ID
        
        Returns:
            Dictionary with success or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if user is a member
        if not group.is_member(user_id):
            return {'error': 'You are not a member of this group'}
        
        # Can't leave if you're the only admin
        if group.is_admin(user_id):
            admin_count = GroupMember.query.filter_by(
                group_id=group_id,
                role='admin',
                is_active=True
            ).count()
            if admin_count <= 1:
                return {'error': 'Cannot leave as the last admin. Transfer admin rights first.'}
        
        try:
            group.remove_member(user_id)
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to leave group: {str(e)}'}
    
    @staticmethod
    def delete_group(
        group_id: int,
        user_id: int
    ) -> dict:
        """
        Delete a group
        
        Args:
            group_id: Group ID
            user_id: ID of the user deleting (must be creator)
        
        Returns:
            Dictionary with success or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Only creator can delete
        if group.created_by != user_id:
            return {'error': 'Only the group creator can delete the group'}
        
        try:
            # Soft delete
            group.delete_group()
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to delete group: {str(e)}'}
    
    @staticmethod
    def get_group_info(group_id: int, user_id: int) -> dict:
        """
        Get group information
        
        Args:
            group_id: Group ID
            user_id: Current user ID
        
        Returns:
            Dictionary with group info or error
        """
        group = Group.query.get(group_id)
        if not group or not group.is_active:
            return {'error': 'Group not found or inactive'}
        
        # Check if user is a member
        if not group.is_member(user_id):
            return {'error': 'You are not a member of this group'}
        
        return {
            'success': True,
            'group': group.to_dict(include_members=True),
            'is_admin': group.is_admin(user_id)
        }
    
    @staticmethod
    def get_user_groups(user_id: int) -> dict:
        """
        Get all groups a user is a member of
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with groups list
        """
        groups = Group.query.join(
            GroupMember,
            GroupMember.group_id == Group.id
        ).filter(
            GroupMember.user_id == user_id,
            GroupMember.is_active == True,
            Group.is_active == True
        ).all()
        
        return {
            'success': True,
            'groups': [group.to_dict() for group in groups],
            'total': len(groups)
        }