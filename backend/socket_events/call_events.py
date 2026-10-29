# backend/socket_events/call_events.py
"""
Signaling relay for 1:1 WebRTC audio/video calls. This server never sees
call media (audio/video) at all — WebRTC streams peer-to-peer once
connected — it only relays the handshake messages (SDP offer/answer, ICE
candidates) neither side can exchange without a channel. Every call event
carries its own JWT like the rest of socket_events/*.py, so the caller/
callee identity on each relayed message is always what the server itself
decoded, never a client-supplied value.

Live call state is tracked in two small in-memory dicts, not the database
— calls are transient (seconds to an hour), and keeping it in-memory means
a server restart just drops any calls in flight rather than leaving stale
"ringing" rows to clean up. That does mean live call state doesn't survive
a restart or work across multiple server processes — fine for a single
dev/small-deployment instance, a real multi-process deployment would need
this in Redis instead.

Only the *outcome* of a finished call (who, when, how long, completed /
missed / declined) is persisted, as one row in `call_logs`
(models/call_log.py), so it can show up in the chat history afterwards.
"""
from flask_socketio import emit
from flask_jwt_extended import decode_token
from flask import request
from datetime import datetime
from extensions import db
from models import User, CallLog
from socket_events.call_state import user_group_call
import logging
import uuid

logger = logging.getLogger(__name__)

# call_id -> {'caller_id', 'callee_id', 'call_type', 'started_at',
#             'answered_at' (None until answered), 'status': 'ringing'|'active'}
_active_calls = {}
# user_id -> call_id, for an O(1) "are they already on a call" check and
# for cleaning up on disconnect.
_user_active_call = {}


def in_one_to_one_call(user_id):
    """True if the user is on (or being rung for) a 1:1 call. Used by the
    group call handlers so nobody ends up in two calls at once."""
    return bool(_user_active_call.get(user_id))


def _record_call(call_id, call, declined=False):
    """
    Persist a finished call and tell both participants (over their personal
    socket rooms) so their open chat can show it immediately.

    Outcome: answered -> 'completed' (duration runs from the answer);
    explicitly rejected -> 'declined'; anything else -> 'missed' (the
    caller gave up first, the callee was busy, or a side dropped while it
    was still ringing).

    This must never raise: it runs in the middle of tearing a call down,
    and a logging problem shouldn't stop the other party being told the
    call has ended.
    """
    try:
        now = datetime.utcnow()
        answered_at = call.get('answered_at')
        if answered_at:
            status = 'completed'
            duration = max(0, int((now - answered_at).total_seconds()))
        elif declined:
            status, duration = 'declined', 0
        else:
            status, duration = 'missed', 0

        log = CallLog(
            call_id=call_id,
            caller_id=call['caller_id'],
            callee_id=call['callee_id'],
            call_type=call.get('call_type', 'audio'),
            status=status,
            started_at=call.get('started_at') or now,
            answered_at=answered_at,
            ended_at=now,
            duration_seconds=duration,
        )
        db.session.add(log)
        db.session.flush()  # assigns log.id so the payload below is complete
        payload = log.to_dict()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to record call {call_id}: {str(e)}")
        return

    try:
        for uid in (call['caller_id'], call['callee_id']):
            emit('call_logged', payload, room=f"user_{uid}")
    except Exception as e:
        logger.error(f"Failed to announce call log for {call_id}: {str(e)}")


def _end_call_internal(call_id, declined=False):
    call = _active_calls.pop(call_id, None)
    if not call:
        return None
    _user_active_call.pop(call['caller_id'], None)
    _user_active_call.pop(call['callee_id'], None)
    # Popping from _active_calls above is what makes this happen exactly
    # once per call, even if both sides hang up at the same instant.
    _record_call(call_id, call, declined=declined)
    return call


def handle_user_disconnected(user_id):
    """
    Called from presence_events.py's disconnect handler (not registered
    as its own socket event — Flask-SocketIO keeps only the last handler
    registered per event name, so a second `@socketio.on('disconnect')`
    here would silently replace presence tracking instead of running
    alongside it). If the disconnecting user was on a call, the other
    party needs to know now, not once they notice the peer connection
    has gone silent.
    """
    call_id = _user_active_call.get(user_id)
    if not call_id:
        return
    call = _end_call_internal(call_id)
    if not call:
        return
    other_id = call['callee_id'] if call['caller_id'] == user_id else call['caller_id']
    emit('call_ended', {'call_id': call_id, 'reason': 'peer_disconnected'}, room=f"user_{other_id}")


def register_call_events(socketio):
    """Register WebRTC call-signaling socket events"""

    def _authed_user_id(data):
        token = data.get('token')
        if not token:
            emit('call_error', {'message': 'Authentication required'})
            return None
        try:
            return int(decode_token(token)['sub'])
        except Exception:
            emit('call_error', {'message': 'Invalid or expired session'})
            return None

    @socketio.on('call_offer')
    def handle_call_offer(data):
        """
        Start a call.
        Data: { to_user_id, offer (SDP dict), call_type: 'audio'|'video', token }
        """
        try:
            caller_id = _authed_user_id(data)
            if not caller_id:
                return

            try:
                callee_id = int(data.get('to_user_id'))
            except (TypeError, ValueError):
                callee_id = None
            offer = data.get('offer')
            call_type = data.get('call_type', 'video')

            if not callee_id or not offer:
                emit('call_error', {'message': 'to_user_id and offer are required'})
                return
            if call_type not in ('audio', 'video'):
                call_type = 'video'
            if callee_id == caller_id:
                emit('call_error', {'message': "You can't call yourself"})
                return

            if _user_active_call.get(caller_id) or user_group_call.get(caller_id):
                emit('call_error', {'message': 'You are already on a call'})
                return
            if _user_active_call.get(callee_id) or user_group_call.get(callee_id):
                emit('call_busy', {'to_user_id': callee_id})
                # The callee's phone never rang, but the attempt still
                # belongs in both users' history as a missed call.
                _record_call(str(uuid.uuid4()), {
                    'caller_id': caller_id,
                    'callee_id': callee_id,
                    'call_type': call_type,
                    'started_at': datetime.utcnow(),
                    'answered_at': None,
                })
                return

            caller = User.query.get(caller_id)
            if not caller:
                emit('call_error', {'message': 'Caller not found'})
                return

            call_id = str(uuid.uuid4())
            _active_calls[call_id] = {
                'caller_id': caller_id,
                'callee_id': callee_id,
                'call_type': call_type,
                'started_at': datetime.utcnow(),
                'answered_at': None,
                'status': 'ringing',
            }
            _user_active_call[caller_id] = call_id
            _user_active_call[callee_id] = call_id

            # The caller needs to know the server-assigned call_id right
            # away, not only once the callee answers — ICE candidates
            # start gathering the moment the offer is created, well
            # before there's any guarantee of a quick answer, and every
            # candidate message needs a call_id to relay against. This
            # goes straight back to the requesting socket (no room
            # needed — it's a direct ack, not a broadcast).
            emit('call_initiated', {'call_id': call_id})

            emit('call_offer', {
                'call_id': call_id,
                'call_type': call_type,
                'offer': offer,
                'from_user': {
                    'id': caller.id,
                    'username': caller.username,
                    'full_name': caller.full_name,
                    'profile_picture': caller.profile_picture,
                },
            }, room=f"user_{callee_id}")

            logger.info(f"Call {call_id}: {caller_id} calling {callee_id} ({call_type})")

        except Exception as e:
            logger.error(f"call_offer error: {str(e)}")
            emit('call_error', {'message': 'Failed to start call'})

    @socketio.on('call_answer')
    def handle_call_answer(data):
        """
        Accept a call.
        Data: { call_id, answer (SDP dict), token }
        """
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return

            call_id = data.get('call_id')
            answer = data.get('answer')
            call = _active_calls.get(call_id)

            if not call or call['callee_id'] != user_id:
                emit('call_error', {'message': 'No such ringing call for you'})
                return

            call['status'] = 'active'
            call['answered_at'] = call.get('answered_at') or datetime.utcnow()
            emit('call_answer', {'call_id': call_id, 'answer': answer}, room=f"user_{call['caller_id']}")

        except Exception as e:
            logger.error(f"call_answer error: {str(e)}")
            emit('call_error', {'message': 'Failed to answer call'})

    @socketio.on('call_ice_candidate')
    def handle_ice_candidate(data):
        """
        Relay one ICE candidate to the other party in the call.
        Data: { call_id, candidate, token }
        """
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return

            call_id = data.get('call_id')
            candidate = data.get('candidate')
            call = _active_calls.get(call_id)
            if not call or user_id not in (call['caller_id'], call['callee_id']):
                return  # Stale/unknown call — candidates can arrive slightly
                # after a call ends; silently dropping is correct here, an
                # error would just be noise for a normal race.

            other_id = call['callee_id'] if call['caller_id'] == user_id else call['caller_id']
            emit('call_ice_candidate', {'call_id': call_id, 'candidate': candidate}, room=f"user_{other_id}")

        except Exception as e:
            logger.error(f"call_ice_candidate error: {str(e)}")

    @socketio.on('call_reject')
    def handle_call_reject(data):
        """
        Decline a ringing call (callee side).
        Data: { call_id, token }
        """
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return

            call_id = data.get('call_id')
            call = _active_calls.get(call_id)
            if not call or call['callee_id'] != user_id:
                return

            _end_call_internal(call_id, declined=True)
            emit('call_rejected', {'call_id': call_id}, room=f"user_{call['caller_id']}")

        except Exception as e:
            logger.error(f"call_reject error: {str(e)}")

    @socketio.on('call_end')
    def handle_call_end(data):
        """
        Hang up — either party, at any point (ringing or active).
        Data: { call_id, token }
        """
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return

            call_id = data.get('call_id')
            call = _active_calls.get(call_id)
            if not call or user_id not in (call['caller_id'], call['callee_id']):
                return

            other_id = call['callee_id'] if call['caller_id'] == user_id else call['caller_id']
            _end_call_internal(call_id)
            emit('call_ended', {'call_id': call_id, 'reason': 'hangup'}, room=f"user_{other_id}")

        except Exception as e:
            logger.error(f"call_end error: {str(e)}")