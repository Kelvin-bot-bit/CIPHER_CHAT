# backend/services/cleanup_service.py
"""
Background job that soft-deletes messages whose expires_at has passed
(disappearing messages). Runs on a simple interval via APScheduler rather
than anything more elaborate (Celery beat, etc.) — this app has no other
background task infrastructure, and a single periodic sweep is enough for
a feature that's inherently approximate anyway (a message "disappears"
within CLEANUP_INTERVAL_SECONDS of its expiry, not to the millisecond).

Note this matches the existing delete_message()'s soft-delete behavior
(just flips is_deleted — see MessageService.delete_message): the encrypted
row still exists in the database afterward, just hidden from every query
that already filters is_deleted == False. That's a pre-existing property
of "delete" in this codebase, not something new introduced here; if you
want expiry to also scrub the encrypted content/keys from the row (a
stronger guarantee), that would need to change delete_message() too, not
just this job.
"""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 10

_scheduler = None


def _cleanup_expired_messages(app):
    with app.app_context():
        from models import Message, GroupMember
        from extensions import db, socketio
        try:
            expired = Message.query.filter(
                Message.expires_at.isnot(None),
                Message.expires_at <= datetime.utcnow(),
                Message.is_deleted == False
            ).all()
            if not expired:
                return

            # Capture what each message needs for the socket broadcast
            # before flipping is_deleted — grabbing this after commit
            # would still work (the columns aren't cleared), but doing it
            # up front keeps the "what to notify" and "what changed in
            # the DB" logic clearly separate.
            to_notify = []
            for message in expired:
                to_notify.append({
                    'id': message.id,
                    'recipient_type': message.recipient_type,
                    'recipient_id': message.recipient_id,
                    'sender_id': message.sender_id,
                })
                message.is_deleted = True
            db.session.commit()
            logger.info(f"Disappearing-messages cleanup: soft-deleted {len(expired)} expired message(s)")

            # Push it out immediately rather than letting each party find
            # out on their next poll — both the sender's and every
            # recipient's open chat window should clear it the moment it
            # actually expires, not whenever they happen to refresh next.
            for m in to_notify:
                payload = {'message_id': m['id'], 'chat_type': m['recipient_type']}
                if m['recipient_type'] == 'user':
                    socketio.emit('message_expired', {**payload, 'chat_id': m['sender_id']}, room=f"user_{m['recipient_id']}")
                    socketio.emit('message_expired', {**payload, 'chat_id': m['recipient_id']}, room=f"user_{m['sender_id']}")
                else:
                    members = GroupMember.query.filter_by(group_id=m['recipient_id'], is_active=True).all()
                    for member in members:
                        socketio.emit('message_expired', {**payload, 'chat_id': m['recipient_id']}, room=f"user_{member.user_id}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Disappearing-messages cleanup error: {str(e)}")


def _purge_status_media(app):
    """Hourly-ish sweep of expired/deleted statuses and their encrypted media."""
    with app.app_context():
        from services.status_service import StatusService
        StatusService.purge_expired()


def start_cleanup_scheduler(app):
    """
    Starts the background cleanup job once per process. Safe to call from
    create_app() even under Flask's debug reloader, which otherwise
    imports the app twice and would start two competing schedulers.
    """
    global _scheduler
    if _scheduler is not None:
        return

    import os
    # Flask's debug reloader re-executes the whole module in a child
    # process with WERKZEUG_RUN_MAIN=true; the parent process (which
    # doesn't serve requests) should skip starting the scheduler so it
    # doesn't run twice.
    if app.config.get('DEBUG') and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        func=lambda: _cleanup_expired_messages(app),
        trigger='interval',
        seconds=CLEANUP_INTERVAL_SECONDS,
        id='expire_messages',
        replace_existing=True,
    )
    _scheduler.add_job(
        func=lambda: _purge_status_media(app),
        trigger='interval',
        minutes=15,
        id='purge_status_media',
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Disappearing-messages cleanup scheduler started (every {CLEANUP_INTERVAL_SECONDS}s)")