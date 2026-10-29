# backend/routes/push.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.push_service import PushService
import logging

push_bp = Blueprint('push', __name__)
logger = logging.getLogger(__name__)


@push_bp.route('/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """
    Returns the VAPID public key the frontend needs to call
    pushManager.subscribe(). Not auth-gated — it's public by design (it's
    sent to the browser's push service on every subscribe call regardless).
    ---
    tags:
      - Push
    responses:
      200:
        description: VAPID public key, or null if push isn't configured
    """
    key = current_app.config.get('VAPID_PUBLIC_KEY')
    return jsonify({'vapid_public_key': key, 'configured': PushService.is_configured()}), 200


@push_bp.route('/subscribe', methods=['POST'])
@jwt_required()
def subscribe():
    """
    Save a browser's push subscription
    ---
    tags:
      - Push
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - endpoint
            - keys
          properties:
            endpoint:
              type: string
            keys:
              type: object
              properties:
                p256dh:
                  type: string
                auth:
                  type: string
    responses:
      200:
        description: Subscription saved
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        endpoint = data.get('endpoint')
        keys = data.get('keys') or {}
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')

        if not endpoint or not p256dh or not auth:
            return jsonify({'error': 'endpoint and keys.p256dh/keys.auth are required'}), 400

        result = PushService.subscribe(
            user_id=user_id,
            endpoint=endpoint,
            p256dh_key=p256dh,
            auth_key=auth,
            user_agent=request.headers.get('User-Agent'),
        )

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify({'message': 'Subscribed to push notifications'}), 200

    except Exception as e:
        logger.error(f"Push subscribe error: {str(e)}")
        return jsonify({'error': 'Failed to subscribe'}), 500


@push_bp.route('/unsubscribe', methods=['POST'])
@jwt_required()
def unsubscribe():
    """
    Remove a browser's push subscription
    ---
    tags:
      - Push
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - endpoint
          properties:
            endpoint:
              type: string
    responses:
      200:
        description: Unsubscribed
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        endpoint = data.get('endpoint')

        if not endpoint:
            return jsonify({'error': 'endpoint is required'}), 400

        result = PushService.unsubscribe(user_id, endpoint)
        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify({'message': 'Unsubscribed'}), 200

    except Exception as e:
        logger.error(f"Push unsubscribe error: {str(e)}")
        return jsonify({'error': 'Failed to unsubscribe'}), 500