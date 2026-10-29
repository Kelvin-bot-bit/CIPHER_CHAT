# backend/services/push_service.py
"""
Sends browser push notifications via the Web Push protocol (VAPID auth),
so a notification reaches the user even when no tab is open — the
in-app/socket notification system only works while the app is running in a
foreground or backgrounded tab.

Requires the `pywebpush` package (`pip install pywebpush`) and a VAPID key
pair configured via VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY (see config.py).
Generate a pair once per deployment with:

    python -c "from py_vapid import Vapid02; v = Vapid02(); v.generate_keys(); \
        print('PUBLIC:', v.public_key); print('PRIVATE:', v.private_key)"

or more simply:

    vapid --gen

(py-vapid installs a `vapid` CLI command). Never commit the private key or
share it between deployments — treat it like any other secret.
"""
import logging
from flask import current_app
from extensions import db
from models import PushSubscription

logger = logging.getLogger(__name__)

try:
    from pywebpush import webpush, WebPushException
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    PYWEBPUSH_AVAILABLE = False


class PushService:

    @staticmethod
    def is_configured() -> bool:
        return bool(
            PYWEBPUSH_AVAILABLE
            and current_app.config.get('VAPID_PUBLIC_KEY')
            and current_app.config.get('VAPID_PRIVATE_KEY')
        )

    @staticmethod
    def subscribe(user_id: int, endpoint: str, p256dh_key: str, auth_key: str, user_agent: str = None) -> dict:
        """Save (or refresh) a browser's push subscription for a user."""
        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if existing:
            existing.user_id = user_id
            existing.p256dh_key = p256dh_key
            existing.auth_key = auth_key
            existing.user_agent = user_agent
            db.session.commit()
            return {'success': True, 'subscription': existing.to_dict()}

        sub = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh_key=p256dh_key,
            auth_key=auth_key,
            user_agent=user_agent,
        )
        db.session.add(sub)
        db.session.commit()
        return {'success': True, 'subscription': sub.to_dict()}

    @staticmethod
    def unsubscribe(user_id: int, endpoint: str) -> dict:
        sub = PushSubscription.query.filter_by(user_id=user_id, endpoint=endpoint).first()
        if not sub:
            return {'error': 'Subscription not found'}
        db.session.delete(sub)
        db.session.commit()
        return {'success': True}

    @staticmethod
    def send_push(user_id: int, title: str, body: str, data: dict = None) -> None:
        """
        Push `title`/`body` to every device the user has subscribed on.
        Best-effort and silent on failure — a missing/misconfigured VAPID
        setup, or a user with no subscriptions, should never block the
        in-app notification this is normally called alongside, so this
        never raises.
        """
        if not PushService.is_configured():
            return

        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
        if not subscriptions:
            return

        payload = {
            'title': title,
            'body': body,
            'data': data or {},
        }

        import json
        vapid_claims = {'sub': f"mailto:{current_app.config['VAPID_CLAIM_EMAIL']}"}

        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {
                            'p256dh': sub.p256dh_key,
                            'auth': sub.auth_key,
                        },
                    },
                    data=json.dumps(payload),
                    vapid_private_key=current_app.config['VAPID_PRIVATE_KEY'],
                    vapid_claims=dict(vapid_claims),
                )
            except WebPushException as e:
                status = getattr(e.response, 'status_code', None)
                if status in (404, 410):
                    # Gone — the browser revoked or expired this
                    # subscription. Clean it up rather than retrying it
                    # forever on every future notification.
                    db.session.delete(sub)
                    db.session.commit()
                else:
                    logger.warning(f"Push send failed for subscription {sub.id}: {e}")
            except Exception as e:
                logger.warning(f"Push send error for subscription {sub.id}: {e}")