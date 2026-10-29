# backend/services/status_service.py
import os
import uuid
import base64
import logging
from datetime import datetime, timedelta
from flask import current_app
from models import User, Friend, StatusPost, StatusRecipientKey, StatusView
from extensions import db
from services.crypto_service import CryptoService
from services.key_management import KeyManagementService
from sqlalchemy import or_
from utils.media_sniff import sniff_media, describe_allowed

logger = logging.getLogger(__name__)

DEFAULT_LIFETIME_HOURS = 24
MAX_IMAGE_SIZE = 15 * 1024 * 1024
# Videos are encrypted/decrypted in memory (as images are), so the cap is what
# keeps a single upload or view from costing too much RAM. Override with the
# STATUS_MAX_VIDEO_MB setting if your server can afford more.
MAX_VIDEO_SIZE = 50 * 1024 * 1024


class StatusService:

    @staticmethod
    def _get_friend_users(user_id: int):
        """Same bidirectional-friendship join as FriendService.get_friends,
        but returning full User objects (not to_dict()s) — the fan-out
        below needs each friend's raw public_key, which the default
        to_dict() doesn't include."""
        return User.query.join(
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

    @staticmethod
    def _max_video_size() -> int:
        try:
            mb = current_app.config.get('STATUS_MAX_VIDEO_MB')
            return int(mb) * 1024 * 1024 if mb else MAX_VIDEO_SIZE
        except (RuntimeError, TypeError, ValueError):
            return MAX_VIDEO_SIZE

    @staticmethod
    def _remove_file(path: str):
        """Best-effort removal of an encrypted media file."""
        if not path:
            return
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"Could not remove status media {path}: {e}")

    @staticmethod
    def create_status(
        user_id: int,
        password: str,
        caption: str = '',
        media_data: bytes = None,
        media_filename: str = None,
        media_mime_type: str = None,
        lifetime_hours: int = DEFAULT_LIFETIME_HOURS,
        background_color: str = None
    ) -> dict:
        """
        Post a status: text, a photo, or a short video (with an optional
        caption). Requires the poster's password (same as sending a
        message) to unlock their private key for signing — posting is
        otherwise the same "fan-out a fresh symmetric key" pattern used
        when creating a group (see GroupService.create_group).

        What the media actually is gets decided from its content, not from
        the filename or Content-Type the client sent (see utils.media_sniff).
        """
        if not caption and not media_data:
            return {'error': 'A status needs either text, a photo or a video'}

        media_kind = None
        if media_data:
            detected = sniff_media(media_data)
            if not detected:
                return {'error': f'Unsupported file. Use {describe_allowed()}.'}
            media_kind, media_mime_type = detected
            limit = StatusService._max_video_size() if media_kind == 'video' else MAX_IMAGE_SIZE
            if len(media_data) > limit:
                label = 'Video' if media_kind == 'video' else 'Photo'
                return {'error': f'{label} is too large ({len(media_data) / 1024 / 1024:.1f}MB). '
                                 f'The limit is {limit // 1024 // 1024}MB.'}

        poster = User.query.get(user_id)
        if not poster:
            return {'error': 'User not found'}

        key_result = KeyManagementService.get_user_private_key(user_id, password)
        if not key_result.get('success'):
            return {'error': key_result.get('error', 'Incorrect password')}
        poster_private_key = key_result['private_key']

        media_path = None
        try:
            status_key = os.urandom(32)

            encrypted = CryptoService.encrypt_with_raw_key(caption or '', status_key, poster_private_key)

            status = StatusPost(
                user_id=user_id,
                message_type=media_kind or 'text',
                encrypted_content=encrypted['encrypted_message'],
                nonce=encrypted['nonce'],
                tag=encrypted['tag'],
                digital_signature=encrypted['signature'],
                background_color=background_color or '#151D22',
                expires_at=datetime.utcnow() + timedelta(hours=lifetime_hours)
            )

            if media_data:
                encrypted_file = CryptoService.encrypt_file(media_data)
                media_raw_key = base64.b64decode(encrypted_file['encryption_key'])

                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'status')
                os.makedirs(upload_dir, exist_ok=True)
                media_path = os.path.join(upload_dir, f"{uuid.uuid4()}.enc")
                with open(media_path, 'wb') as f:
                    f.write(encrypted_file['encrypted_data'])
                del encrypted_file['encrypted_data']  # free the ciphertext copy early

                wrap = CryptoService.wrap_key_with_raw_key(media_raw_key, status_key)

                status.image_path = media_path
                status.image_mime_type = media_mime_type
                status.image_size = len(media_data)
                status.image_iv = encrypted_file['nonce']
                status.image_wrapped_key = wrap['wrapped_key']
                status.image_wrap_nonce = wrap['wrap_nonce']

            db.session.add(status)
            db.session.commit()

            # Fan out: the poster's own copy, plus one per current friend.
            # Anyone who becomes a friend later never gets a key for this
            # post — see the StatusPost docstring.
            recipients = [poster] + StatusService._get_friend_users(user_id)
            for recipient in recipients:
                key_row = StatusRecipientKey(
                    status_id=status.id,
                    user_id=recipient.id,
                    encrypted_status_key=CryptoService.encrypt_group_key(status_key, recipient.public_key)
                )
                db.session.add(key_row)
            db.session.commit()

            # Push to each friend's status tray immediately rather than
            # leaving it to their next feed fetch — deliberately no
            # Notification row alongside this (unlike a message or friend
            # request): a push notification per friend for every status
            # update would be far noisier than this feature should be.
            from extensions import socketio
            for recipient in recipients:
                if recipient.id == user_id:
                    continue
                socketio.emit('new_status', {'user_id': user_id, 'status_id': status.id}, room=f"user_{recipient.id}")

            return {'success': True, 'status': status.to_dict()}

        except Exception as e:
            db.session.rollback()
            # Don't leave an encrypted video orphaned on disk if the post failed.
            StatusService._remove_file(media_path)
            logger.error(f"Create status error: {str(e)}")
            return {'error': f'Failed to post status: {str(e)}'}

    @staticmethod
    def get_feed(user_id: int) -> dict:
        """
        Every active (not expired, not deleted) status the current user
        has a key for — their own, plus every friend's — grouped by
        poster for the frontend to render as a story rail.
        """
        now = datetime.utcnow()
        rows = db.session.query(StatusPost, StatusRecipientKey).join(
            StatusRecipientKey, StatusRecipientKey.status_id == StatusPost.id
        ).filter(
            StatusRecipientKey.user_id == user_id,
            StatusPost.is_deleted == False,
            StatusPost.expires_at > now
        ).order_by(StatusPost.created_at.desc()).all()

        viewed_ids = {
            v.status_id for v in StatusView.query.filter_by(viewer_id=user_id).all()
        }

        by_user = {}
        for status, _key_row in rows:
            poster = User.query.get(status.user_id)
            if not poster:
                continue
            entry = by_user.setdefault(status.user_id, {
                'user': {
                    'id': poster.id,
                    'username': poster.username,
                    'full_name': poster.full_name,
                    'profile_picture': poster.profile_picture,
                },
                'statuses': [],
                'has_unseen': False,
            })
            item = status.to_dict()
            item['viewed'] = status.id in viewed_ids
            entry['statuses'].append(item)
            if not item['viewed'] and status.user_id != user_id:
                entry['has_unseen'] = True

        return {'success': True, 'feed': list(by_user.values())}

    @staticmethod
    def view_status(status_id: int, viewer_id: int, password: str) -> dict:
        """Decrypt a status's caption and record the view (unless the
        viewer is the poster themself — you don't "view" your own post)."""
        status = StatusPost.query.get(status_id)
        if not status or status.is_deleted:
            return {'error': 'Status not found'}
        if status.expires_at and status.expires_at <= datetime.utcnow():
            return {'error': 'This status has expired'}

        key_row = StatusRecipientKey.query.filter_by(status_id=status_id, user_id=viewer_id).first()
        if not key_row:
            return {'error': 'You do not have access to this status'}

        key_result = KeyManagementService.get_user_private_key(viewer_id, password)
        if not key_result.get('success'):
            return {'error': key_result.get('error', 'Incorrect password')}

        try:
            status_key = CryptoService.decrypt_group_key(key_row.encrypted_status_key, key_result['private_key'])
            poster = User.query.get(status.user_id)
            decrypted = CryptoService.decrypt_with_raw_key(
                {
                    'encrypted_message': status.encrypted_content,
                    'nonce': status.nonce,
                    'signature': status.digital_signature,
                },
                status_key,
                poster.public_key
            )

            if viewer_id != status.user_id:
                existing = StatusView.query.filter_by(status_id=status_id, viewer_id=viewer_id).first()
                if not existing:
                    db.session.add(StatusView(status_id=status_id, viewer_id=viewer_id))
                    db.session.commit()

            result = status.to_dict()
            result['caption'] = decrypted['decrypted_message']
            result['is_valid_signature'] = decrypted['is_valid_signature']
            return {'success': True, 'status': result}

        except Exception as e:
            logger.error(f"View status error: {str(e)}")
            return {'error': f'Failed to decrypt status: {str(e)}'}

    @staticmethod
    def get_status_media(status_id: int, viewer_id: int, password: str) -> dict:
        """Decrypt a status's photo or video for a viewer who holds a key for it."""
        status = StatusPost.query.get(status_id)
        if not status or status.is_deleted or not status.image_path:
            return {'error': 'Status media not found'}
        if status.expires_at and status.expires_at <= datetime.utcnow():
            return {'error': 'This status has expired'}

        key_row = StatusRecipientKey.query.filter_by(status_id=status_id, user_id=viewer_id).first()
        if not key_row:
            return {'error': 'You do not have access to this status'}

        key_result = KeyManagementService.get_user_private_key(viewer_id, password)
        if not key_result.get('success'):
            return {'error': key_result.get('error', 'Incorrect password')}

        try:
            status_key = CryptoService.decrypt_group_key(key_row.encrypted_status_key, key_result['private_key'])
            media_raw_key = CryptoService.unwrap_key_with_raw_key(
                status.image_wrapped_key, status.image_wrap_nonce, status_key
            )
            with open(status.image_path, 'rb') as f:
                encrypted_data = f.read()
            decrypted_data = CryptoService.decrypt_file(
                encrypted_data, base64.b64encode(media_raw_key).decode('utf-8'), status.image_iv
            )
            return {
                'success': True,
                'media_data': decrypted_data,
                'mime_type': status.image_mime_type,
                'media_type': status.media_type,
            }
        except FileNotFoundError:
            logger.error(f"Status {status_id} media file is missing on disk")
            return {'error': 'This status media is no longer available'}
        except Exception as e:
            logger.error(f"Get status media error: {str(e)}")
            return {'error': f'Failed to decrypt status media: {str(e)}'}

    # Older name, kept so existing callers keep working.
    @staticmethod
    def get_status_image(status_id: int, viewer_id: int, password: str) -> dict:
        result = StatusService.get_status_media(status_id, viewer_id, password)
        if result.get('success'):
            result['image_data'] = result['media_data']
        return result

    @staticmethod
    def get_viewers(status_id: int, requester_id: int) -> dict:
        status = StatusPost.query.get(status_id)
        if not status:
            return {'error': 'Status not found'}
        if status.user_id != requester_id:
            return {'error': 'Only the poster can see who has viewed this status'}
        views = StatusView.query.filter_by(status_id=status_id).order_by(StatusView.viewed_at.desc()).all()
        viewers = []
        for v in views:
            user = User.query.get(v.viewer_id)
            if user:
                viewers.append({
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'profile_picture': user.profile_picture,
                    'viewed_at': v.viewed_at.isoformat() + 'Z',
                })
        return {'success': True, 'viewers': viewers, 'total': len(viewers)}

    @staticmethod
    def delete_status(status_id: int, user_id: int) -> dict:
        status = StatusPost.query.get(status_id)
        if not status:
            return {'error': 'Status not found'}
        if status.user_id != user_id:
            return {'error': 'You can only delete your own status'}
        status.is_deleted = True
        db.session.commit()
        # Deleting means gone: don't leave the encrypted media on disk until
        # the next sweep.
        StatusService._remove_file(status.image_path)
        return {'success': True}

    @staticmethod
    def purge_expired(grace_minutes: int = 60) -> dict:
        """
        Remove statuses that are deleted or expired (plus a short grace
        period) together with their encrypted media files, keys and view
        records, and sweep media files that no status refers to any more
        (e.g. left behind by an upload that failed half-way).

        Run periodically by the background scheduler. Before this existed,
        expired status media stayed on disk forever, which is negligible for
        photos but not for videos.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=grace_minutes)
        removed_rows = removed_files = 0
        try:
            stale = StatusPost.query.filter(
                or_(StatusPost.is_deleted == True, StatusPost.expires_at <= cutoff)  # noqa: E712
            ).all()
            for status in stale:
                if status.image_path:
                    StatusService._remove_file(status.image_path)
                    removed_files += 1
                # Explicit, so it also holds where the database does not
                # enforce ON DELETE CASCADE.
                StatusRecipientKey.query.filter_by(status_id=status.id).delete()
                StatusView.query.filter_by(status_id=status.id).delete()
                db.session.delete(status)
                removed_rows += 1
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Status purge error: {str(e)}")
            return {'error': str(e)}

        orphans = StatusService._sweep_orphans()
        if removed_rows or orphans:
            logger.info(f"Status cleanup: removed {removed_rows} expired/deleted status(es), "
                        f"{removed_files} media file(s), {orphans} orphaned file(s)")
        return {'statuses': removed_rows, 'files': removed_files, 'orphans': orphans}

    @staticmethod
    def _sweep_orphans(min_age_hours: int = 24) -> int:
        folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'status')
        if not os.path.isdir(folder):
            return 0
        referenced = {
            os.path.basename(p) for (p,) in db.session.query(StatusPost.image_path)
            .filter(StatusPost.image_path.isnot(None)).all()
        }
        cutoff = datetime.utcnow().timestamp() - min_age_hours * 3600
        removed = 0
        with os.scandir(folder) as it:
            for entry in it:
                # The age guard avoids racing an upload that has written its
                # file but not yet committed its row.
                if (entry.is_file() and entry.name.endswith('.enc') and entry.name not in referenced
                        and entry.stat().st_mtime < cutoff):
                    StatusService._remove_file(entry.path)
                    removed += 1
        return removed
