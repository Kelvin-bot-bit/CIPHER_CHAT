# backend/routes/groups.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.group_service import GroupService
from services.message_service import MessageService
from services.notification_service import NotificationService
from models import Group, User
from extensions import db
import logging

groups_bp = Blueprint('groups', __name__)
logger = logging.getLogger(__name__)

@groups_bp.route('/', methods=['POST'])
@jwt_required()
def create_group():
    """
    Create a new group
    ---
    tags:
      - Groups
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - group_name
          properties:
            group_name:
              type: string            description:
              type: string
            is_private:
              type: boolean
            member_ids:
              type: array
              items:
                type: integer
    responses:
      200:
        description: Group created successfully
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('group_name'):
            return jsonify({'error': 'Group name is required'}), 400
        
        result = GroupService.create_group(
            creator_id=user_id,
            group_name=data['group_name'],
            description=data.get('description'),
            is_private=data.get('is_private', False),
            member_ids=data.get('member_ids', [])
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Group created successfully',
            'group': result['group']
        }), 201
        
    except Exception as e:
        logger.error(f"Create group error: {str(e)}")
        return jsonify({'error': 'Failed to create group'}), 500

@groups_bp.route('/<int:group_id>/members', methods=['POST'])
@jwt_required()
def add_member(group_id):
    """
    Add a member to a group
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
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
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - user_id
            - password
          properties:
            user_id:
              type: integer
            password:
              type: string
              description: Adding admin's password, needed to unwrap the group key for re-wrapping
    responses:
      200:
        description: Member added successfully
    """
    try:
        admin_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('user_id'):
            return jsonify({'error': 'User ID is required'}), 400
        
        result = GroupService.add_member_to_group(
            group_id=group_id,
            admin_id=admin_id,
            user_id=data['user_id'],
            admin_password=data.get('password')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Member added successfully',
            'member': result.get('member')
        }), 200
        
    except Exception as e:
        logger.error(f"Add member error: {str(e)}")
        return jsonify({'error': 'Failed to add member'}), 500

@groups_bp.route('/<int:group_id>/members/<int:user_id>', methods=['DELETE'])
@jwt_required()
def remove_member(group_id, user_id):
    """
    Remove a member from a group
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
      - name: user_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Member removed successfully
    """
    try:
        admin_id = int(get_jwt_identity())
        
        result = GroupService.remove_member_from_group(
            group_id=group_id,
            admin_id=admin_id,
            user_id=user_id
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Member removed successfully'}), 200
        
    except Exception as e:
        logger.error(f"Remove member error: {str(e)}")
        return jsonify({'error': 'Failed to remove member'}), 500

@groups_bp.route('/<int:group_id>/promote/<int:user_id>', methods=['POST'])
@jwt_required()
def promote_to_admin(group_id, user_id):
    """
    Promote a member to admin
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
      - name: user_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Member promoted to admin
    """
    try:
        admin_id = int(get_jwt_identity())
        
        result = GroupService.promote_to_admin(
            group_id=group_id,
            admin_id=admin_id,
            user_id=user_id
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Member promoted to admin',
            'user_id': result.get('user_id'),
            'new_role': result.get('new_role')
        }), 200
        
    except Exception as e:
        logger.error(f"Promote to admin error: {str(e)}")
        return jsonify({'error': 'Failed to promote member'}), 500

@groups_bp.route('/<int:group_id>/demote/<int:user_id>', methods=['POST'])
@jwt_required()
def demote_from_admin(group_id, user_id):
    """
    Demote an admin to member
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
      - name: user_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Admin demoted to member
    """
    try:
        admin_id = int(get_jwt_identity())
        
        result = GroupService.demote_from_admin(
            group_id=group_id,
            admin_id=admin_id,
            user_id=user_id
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'Admin demoted to member',
            'user_id': result.get('user_id'),
            'new_role': result.get('new_role')
        }), 200
        
    except Exception as e:
        logger.error(f"Demote from admin error: {str(e)}")
        return jsonify({'error': 'Failed to demote admin'}), 500

@groups_bp.route('/<int:group_id>/leave', methods=['POST'])
@jwt_required()
def leave_group(group_id):
    """
    Leave a group
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Left group successfully
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = GroupService.leave_group(user_id, group_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Left group successfully'}), 200
        
    except Exception as e:
        logger.error(f"Leave group error: {str(e)}")
        return jsonify({'error': 'Failed to leave group'}), 500

@groups_bp.route('/<int:group_id>', methods=['DELETE'])
@jwt_required()
def delete_group(group_id):
    """
    Delete a group
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Group deleted successfully
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = GroupService.delete_group(group_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Group deleted successfully'}), 200
        
    except Exception as e:
        logger.error(f"Delete group error: {str(e)}")
        return jsonify({'error': 'Failed to delete group'}), 500

@groups_bp.route('/<int:group_id>', methods=['GET'])
@jwt_required()
def get_group_info(group_id):
    """
    Get group information
    ---
    tags:
      - Groups
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Group information retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = GroupService.get_group_info(group_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get group info error: {str(e)}")
        return jsonify({'error': 'Failed to get group info'}), 500

@groups_bp.route('/my-groups', methods=['GET'])
@jwt_required()
def get_my_groups():
    """
    Get user's groups
    ---
    tags:
      - Groups
    responses:
      200:
        description: User's groups retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = GroupService.get_user_groups(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get user groups error: {str(e)}")
        return jsonify({'error': 'Failed to get user groups'}), 500