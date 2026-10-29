# backend/socket_events/group_call_events.py
"""
Group call signaling for the WebRTC mesh the frontend builds
(frontend/src/context/GroupCallContext.jsx).

How a call flows
----------------
1. A group member emits `group_call_start`. They get `group_call_initiated`
   (with the call_id) and every other member gets `group_call_incoming`.
2. An invitee who accepts emits `group_call_join`. The server sends the
   joiner `group_call_existing_participants` (who is already in) and tells
   each of those people `group_call_participant_joined`. The JOINER then
   sends an offer to each existing participant, so the two sides of a link
   never both offer at once.
3. Offers, answers and ICE candidates are relayed point to point
   (`group_call_offer` / `_answer` / `_ice_candidate`); the server never
   looks inside them.
4. Someone emits `group_call_leave` (or their socket drops) and the rest
   get `group_call_participant_left`. An invitee who says no emits
   `group_call_reject` and the people in the call get
   `group_call_participant_declined`.
5. When the last participant leaves the call is over: it is written to
   `group_call_logs`, every member gets `group_call_logged` so an open chat
   shows it immediately, and anyone whose invite was still ringing gets
   `group_call_ended` so their incoming-call screen goes away.

Failures use `group_call_error`, deliberately not the 1:1 `call_error`, so a
problem with one kind of call doesn't pop an error toast for the other.

Relays go to the exact socket (sid) a participant joined on, not to their
personal room: with two tabs open, an idle second tab must not receive an
offer and answer it. For the same reason a disconnect only removes a
participant if it is the socket they joined from.

Live state is in-memory only, like the 1:1 calls (see call_events.py), and
a mesh gets heavy fast, hence the participant cap.
"""
from flask_socketio import emit
from flask_jwt_extended import decode_token
from flask import request
from datetime import datetime
from extensions import db
from models import User, Group, GroupCallLog
from socket_events.call_events import in_one_to_one_call
from socket_events.call_state import user_group_call
import json
import logging
import uuid

logger = logging.getLogger(__name__)

# Every participant holds a connection to every other one, so each extra
# person adds a stream to upload and download for everybody.
MAX_PARTICIPANTS = 6

# call_id -> {
#   'group_id', 'group_name', 'call_type', 'started_by', 'started_at',
#   'invited': set(user_id)        every other member at the time it started
#   'declined': set(user_id)
#   'participants': {user_id: {'sid', 'joined_at'}}   currently in the call
#   'users': {user_id: {id, username, full_name, profile_picture}}
#   'ever_joined': [user_id]       in join order, starter first (for the log)
#   'first_join_at': datetime|None when someone other than the starter joined
# }
_group_calls = {}
# group_id -> call_id: one live call per group at a time
_group_active_call = {}


def _is_busy(user_id):
    return bool(in_one_to_one_call(user_id) or user_group_call.get(user_id))


def _user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'profile_picture': user.profile_picture,
    }


def _send(call, user_id, event, payload):
    """Send to the socket this participant joined the call on."""
    participant = call['participants'].get(user_id)
    if participant:
        emit(event, payload, room=participant['sid'])


def _finish_call(call_id):
    """The last participant is gone: log the call and tell everyone."""
    call = _group_calls.pop(call_id, None)
    if not call:
        return
    _group_active_call.pop(call['group_id'], None)
    for uid in list(call['participants']):
        user_group_call.pop(uid, None)

    now = datetime.utcnow()
    first_join = call.get('first_join_at')
    duration = max(0, int((now - first_join).total_seconds())) if first_join else 0

    payload = None
    try:
        log = GroupCallLog(
            call_id=call_id,
            group_id=call['group_id'],
            started_by=call['started_by'],
            call_type=call['call_type'],
            started_at=call['started_at'],
            ended_at=now,
            duration_seconds=duration,
            participants_json=json.dumps(call['ever_joined']),
        )
        db.session.add(log)
        db.session.flush()  # assigns log.id so the payload is complete
        payload = log.to_dict()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        payload = None
        logger.error(f"Failed to record group call {call_id}: {str(e)}")

    # None of this may raise: the call is already over either way.
    try:
        ever_joined = set(call['ever_joined'])
        for uid in call['invited'] - ever_joined - call['declined']:
            emit('group_call_ended', {'call_id': call_id}, room=f"user_{uid}")
        if payload:
            for uid in call['invited'] | ever_joined:
                emit('group_call_logged', payload, room=f"user_{uid}")
    except Exception as e:
        logger.error(f"Failed to announce end of group call {call_id}: {str(e)}")


def _remove_participant(call_id, user_id):
    call = _group_calls.get(call_id)
    if not call or user_id not in call['participants']:
        return
    call['participants'].pop(user_id)
    if user_group_call.get(user_id) == call_id:
        user_group_call.pop(user_id, None)

    for uid in list(call['participants']):
        _send(call, uid, 'group_call_participant_left', {'call_id': call_id, 'user_id': user_id})

    if not call['participants']:
        _finish_call(call_id)


def _decline(call_id, user_id):
    call = _group_calls.get(call_id)
    if (
        not call
        or user_id not in call['invited']
        or user_id in call['participants']
        or user_id in call['declined']
    ):
        return
    call['declined'].add(user_id)

    user = call['users'].get(user_id)
    if not user:
        found = User.query.get(user_id)
        user = _user_payload(found) if found else {'id': user_id}

    for uid in list(call['participants']):
        _send(call, uid, 'group_call_participant_declined',
              {'call_id': call_id, 'user_id': user_id, 'user': user})


def handle_group_call_disconnect(user_id, sid):
    """
    Called from presence_events.py's disconnect handler (a second
    `@socketio.on('disconnect')` here would replace presence tracking, since
    Flask-SocketIO keeps one handler per event). Only removes the user if
    this is the socket they joined the call from, so closing an unrelated
    tab doesn't drop them.
    """
    call_id = user_group_call.get(user_id)
    call = _group_calls.get(call_id) if call_id else None
    if not call:
        user_group_call.pop(user_id, None)  # drop a stale pointer
        return
    participant = call['participants'].get(user_id)
    if participant and participant['sid'] == sid:
        _remove_participant(call_id, user_id)


def register_group_call_events(socketio):
    """Register group call signaling socket events"""

    def _authed_user_id(data):
        token = data.get('token')
        if not token:
            emit('group_call_error', {'message': 'Authentication required'})
            return None
        try:
            return int(decode_token(token)['sub'])
        except Exception:
            emit('group_call_error', {'message': 'Invalid or expired session'})
            return None

    @socketio.on('group_call_start')
    def handle_group_call_start(data):
        """
        Start a group call.
        Data: { group_id, call_type: 'audio'|'video', token }
        """
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return

            try:
                group_id = int(data.get('group_id'))
            except (TypeError, ValueError):
                group_id = None
            call_type = data.get('call_type', 'video')
            if call_type not in ('audio', 'video'):
                call_type = 'video'

            if not group_id:
                emit('group_call_error', {'message': 'group_id is required'})
                return

            group = Group.query.get(group_id)
            if not group or not group.is_active:
                emit('group_call_error', {'message': 'Group not found'})
                return
            if not group.is_member(user_id):
                emit('group_call_error', {'message': "You're not a member of this group"})
                return
            if _is_busy(user_id):
                emit('group_call_error', {'message': 'You are already on a call'})
                return
            if group_id in _group_active_call:
                emit('group_call_error', {'message': 'A call is already in progress in this group'})
                return

            starter = User.query.get(user_id)
            if not starter:
                emit('group_call_error', {'message': 'User not found'})
                return

            call_id = str(uuid.uuid4())
            now = datetime.utcnow()
            starter_info = _user_payload(starter)
            invited = {uid for uid in group.get_member_ids() if uid != user_id}

            _group_calls[call_id] = {
                'group_id': group_id,
                'group_name': group.group_name,
                'call_type': call_type,
                'started_by': user_id,
                'started_at': now,
                'invited': invited,
                'declined': set(),
                'participants': {user_id: {'sid': request.sid, 'joined_at': now}},
                'users': {user_id: starter_info},
                'ever_joined': [user_id],
                'first_join_at': None,
            }
            _group_active_call[group_id] = call_id
            user_group_call[user_id] = call_id

            emit('group_call_initiated', {'call_id': call_id})

            for uid in invited:
                # Someone already on another call can't take this one; they
                # simply miss it (and see it as missed in the chat history).
                if _is_busy(uid):
                    continue
                emit('group_call_incoming', {
                    'call_id': call_id,
                    'group_id': group_id,
                    'group_name': group.group_name,
                    'call_type': call_type,
                    'from_user': starter_info,
                }, room=f"user_{uid}")

        except Exception as e:
            logger.error(f"Group call start error: {str(e)}", exc_info=True)
            emit('group_call_error', {'message': 'Failed to start the call'})

    @socketio.on('group_call_join')
    def handle_group_call_join(data):
        """
        Join a call you were invited to.
        Data: { call_id, token }
        """
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return

            call_id = data.get('call_id')
            call = _group_calls.get(call_id)
            if not call:
                emit('group_call_error', {'message': 'This call has already ended'})
                return
            if user_id not in call['invited']:
                emit('group_call_error', {'message': 'You were not invited to this call'})
                return

            existing = call['participants'].get(user_id)
            if existing:
                # A repeated join from the same socket is harmless; from a
                # different tab it must not be allowed to double up.
                if existing['sid'] != request.sid:
                    emit('group_call_error', {'message': "You're already in this call on another tab or device"})
                return
            if _is_busy(user_id):
                emit('group_call_error', {'message': 'You are already on a call'})
                return
            if len(call['participants']) >= MAX_PARTICIPANTS:
                emit('group_call_error', {'message': f'This call is full (up to {MAX_PARTICIPANTS} people)'})
                return

            user = User.query.get(user_id)
            if not user:
                emit('group_call_error', {'message': 'User not found'})
                return
            user_info = _user_payload(user)
            now = datetime.utcnow()

            # People already in the call hear about the newcomer first, so
            # they have registered the tile before its offer arrives.
            already_in = [call['users'][uid] for uid in call['participants']]
            for uid in list(call['participants']):
                _send(call, uid, 'group_call_participant_joined', {'call_id': call_id, 'user': user_info})

            call['participants'][user_id] = {'sid': request.sid, 'joined_at': now}
            call['users'][user_id] = user_info
            call['declined'].discard(user_id)
            if user_id not in call['ever_joined']:
                call['ever_joined'].append(user_id)
            if call['first_join_at'] is None:
                call['first_join_at'] = now
            user_group_call[user_id] = call_id

            emit('group_call_existing_participants', {'call_id': call_id, 'participants': already_in})

        except Exception as e:
            logger.error(f"Group call join error: {str(e)}", exc_info=True)
            emit('group_call_error', {'message': 'Failed to join the call'})

    def _relay(event, data, payload_key):
        """Forward an offer / answer / ICE candidate to one participant."""
        user_id = _authed_user_id(data)
        if not user_id:
            return
        call = _group_calls.get(data.get('call_id'))
        try:
            to_id = int(data.get('to_user_id'))
        except (TypeError, ValueError):
            return
        body = data.get(payload_key)
        # Both ends must be in the call. A mismatch is normal around the
        # moment someone leaves, so drop it quietly instead of erroring.
        if not call or body is None:
            return
        if user_id not in call['participants'] or to_id not in call['participants']:
            return
        emit(event, {
            'call_id': data.get('call_id'),
            'from_user_id': user_id,
            payload_key: body,
        }, room=call['participants'][to_id]['sid'])

    @socketio.on('group_call_offer')
    def handle_group_call_offer(data):
        """Data: { call_id, to_user_id, offer, token }"""
        try:
            _relay('group_call_offer', data, 'offer')
        except Exception as e:
            logger.error(f"Group call offer error: {str(e)}", exc_info=True)

    @socketio.on('group_call_answer')
    def handle_group_call_answer(data):
        """Data: { call_id, to_user_id, answer, token }"""
        try:
            _relay('group_call_answer', data, 'answer')
        except Exception as e:
            logger.error(f"Group call answer error: {str(e)}", exc_info=True)

    @socketio.on('group_call_ice_candidate')
    def handle_group_call_ice_candidate(data):
        """Data: { call_id, to_user_id, candidate, token }"""
        try:
            _relay('group_call_ice_candidate', data, 'candidate')
        except Exception as e:
            logger.error(f"Group call ICE candidate error: {str(e)}", exc_info=True)

    @socketio.on('group_call_reject')
    def handle_group_call_reject(data):
        """Decline an invite. Data: { call_id, token }"""
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return
            _decline(data.get('call_id'), user_id)
        except Exception as e:
            logger.error(f"Group call reject error: {str(e)}", exc_info=True)

    @socketio.on('group_call_leave')
    def handle_group_call_leave(data):
        """Leave a call. Data: { call_id, token }"""
        try:
            user_id = _authed_user_id(data)
            if not user_id:
                return
            call_id = data.get('call_id')
            call = _group_calls.get(call_id)
            if not call:
                return
            if user_id in call['participants']:
                _remove_participant(call_id, user_id)
            else:
                # The client also sends "leave" when an invitee accepted but
                # couldn't get a camera/mic. That's really a decline.
                _decline(call_id, user_id)
        except Exception as e:
            logger.error(f"Group call leave error: {str(e)}", exc_info=True)
