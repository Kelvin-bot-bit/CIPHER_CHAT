# backend/routes/calls.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import and_, or_
from models import CallLog, GroupCallLog, Group
import logging

calls_bp = Blueprint('calls', __name__)
logger = logging.getLogger(__name__)


@calls_bp.route('/history/<int:peer_id>', methods=['GET'])
@jwt_required()
def get_call_history(peer_id):
    """
    Finished 1:1 calls between the current user and one other user, oldest
    first, so the chat window can show them in the conversation timeline.
    ---
    tags:
      - Calls
    parameters:
      - name: peer_id
        in: path
        required: true
        type: integer
      - name: limit
        in: query
        type: integer
        default: 100
    responses:
      200:
        description: Call history retrieved successfully
      401:
        description: Unauthorized
    """
    try:
        user_id = int(get_jwt_identity())
        try:
            limit = max(1, min(int(request.args.get('limit', 100)), 200))
        except (TypeError, ValueError):
            limit = 100

        logs = (
            CallLog.query.filter(
                or_(
                    and_(CallLog.caller_id == user_id, CallLog.callee_id == peer_id),
                    and_(CallLog.caller_id == peer_id, CallLog.callee_id == user_id),
                )
            )
            .order_by(CallLog.ended_at.desc())
            .limit(limit)
            .all()
        )
        logs.reverse()
        return jsonify({'calls': [log.to_dict() for log in logs]}), 200

    except Exception as e:
        logger.error(f"Get call history error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get call history'}), 500


@calls_bp.route('/group/<int:group_id>', methods=['GET'])
@jwt_required()
def get_group_call_history(group_id):
    """
    Finished group calls for one group, oldest first, for members only.
    ---
    tags:
      - Calls
    parameters:
      - name: group_id
        in: path
        required: true
        type: integer
      - name: limit
        in: query
        type: integer
        default: 100
    responses:
      200:
        description: Group call history retrieved successfully
      403:
        description: Not a member of this group
      404:
        description: Group not found
    """
    try:
        user_id = int(get_jwt_identity())

        group = Group.query.get(group_id)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        if not group.is_member(user_id):
            return jsonify({'error': 'You are not a member of this group'}), 403

        try:
            limit = max(1, min(int(request.args.get('limit', 100)), 200))
        except (TypeError, ValueError):
            limit = 100

        logs = (
            GroupCallLog.query.filter_by(group_id=group_id)
            .order_by(GroupCallLog.ended_at.desc())
            .limit(limit)
            .all()
        )
        logs.reverse()
        return jsonify({'calls': [log.to_dict() for log in logs]}), 200

    except Exception as e:
        logger.error(f"Get group call history error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to get group call history'}), 500
