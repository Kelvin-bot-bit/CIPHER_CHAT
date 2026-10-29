# backend/socket_events/call_state.py
"""
State shared between the 1:1 call handlers (call_events.py) and the group
call handlers (group_call_events.py), so a user can only ever be in one
call at a time, whichever kind it is.

Live call state is in-memory only (see call_events.py for why).
"""

# user_id -> call_id of the GROUP call the user has joined. (1:1 calls keep
# their own equivalent map inside call_events.py.)
user_group_call = {}
