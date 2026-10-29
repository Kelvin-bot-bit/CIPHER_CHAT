# backend/socket_events/__init__.py
"""
Socket Events package for Secure Chat Application
Real-time communication handlers
"""

from .chat_events import register_chat_events
from .typing_events import register_typing_events
from .presence_events import register_presence_events

__all__ = [
    'register_chat_events',
    'register_typing_events',
    'register_presence_events'
]