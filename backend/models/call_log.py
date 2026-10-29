# backend/models/call_log.py
import json
from datetime import datetime
from extensions import db
from sqlalchemy import Enum, Index


class CallLog(db.Model):
    """
    One row per finished 1:1 call, written by the call-signaling code
    (socket_events/call_events.py) the moment a call ends.

    Deliberately NOT stored in the `messages` table: every message there
    carries an end-to-end encrypted body plus the sender's digital
    signature, neither of which the server can produce on a user's behalf.
    A call record has no secret content anyway - the server already sees
    who called whom and when, because it relays the signaling - so this
    holds only that metadata (no media, no SDP, no ICE candidates).
    """
    __tablename__ = 'call_logs'

    id = db.Column(db.Integer, primary_key=True)
    # The id the signaling layer assigned to the call (a UUID string).
    call_id = db.Column(db.String(36), unique=True, nullable=False)
    caller_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    callee_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    call_type = db.Column(Enum('audio', 'video'), nullable=False)
    # completed: the callee answered. missed: nobody answered (the caller
    # hung up first, the callee was busy, or the line dropped while
    # ringing). declined: the callee explicitly rejected it.
    status = db.Column(Enum('completed', 'missed', 'declined'), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    answered_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime, nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        Index('idx_call_logs_caller', 'caller_id', 'ended_at'),
        Index('idx_call_logs_callee', 'callee_id', 'ended_at'),
    )

    def to_dict(self):
        def iso(dt):
            return dt.isoformat() + 'Z' if dt else None

        return {
            'id': self.id,
            'call_id': self.call_id,
            'caller_id': self.caller_id,
            'callee_id': self.callee_id,
            'call_type': self.call_type,
            'status': self.status,
            'started_at': iso(self.started_at),
            'answered_at': iso(self.answered_at),
            'ended_at': iso(self.ended_at),
            'duration_seconds': self.duration_seconds or 0,
        }


class GroupCallLog(db.Model):
    """
    One row per finished group call, written when the last participant
    leaves (socket_events/group_call_events.py). Same reasoning as CallLog:
    just metadata, kept out of the encrypted `messages` table.

    `participants_json` is the ordered list of user ids who actually joined
    (the starter first), stored as plain JSON text so it works on any
    MySQL/MariaDB version. Anyone in the group who is NOT in that list
    missed the call.
    """
    __tablename__ = 'group_call_logs'

    id = db.Column(db.Integer, primary_key=True)
    call_id = db.Column(db.String(36), unique=True, nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    started_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    call_type = db.Column(Enum('audio', 'video'), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=False)
    # Counted from when the first other person joined; 0 if nobody did.
    duration_seconds = db.Column(db.Integer, nullable=False, default=0)
    participants_json = db.Column(db.Text, nullable=False, default='[]')

    __table_args__ = (
        Index('idx_group_call_logs_group', 'group_id', 'ended_at'),
    )

    def to_dict(self):
        try:
            participant_ids = json.loads(self.participants_json or '[]')
        except (TypeError, ValueError):
            participant_ids = []

        return {
            'id': self.id,
            'call_id': self.call_id,
            'group_id': self.group_id,
            'started_by': self.started_by,
            'call_type': self.call_type,
            'started_at': self.started_at.isoformat() + 'Z' if self.started_at else None,
            'ended_at': self.ended_at.isoformat() + 'Z' if self.ended_at else None,
            'duration_seconds': self.duration_seconds or 0,
            'participant_ids': participant_ids,
        }
