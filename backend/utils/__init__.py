# backend/utils/__init__.py
"""
Utilities package for Secure Chat Application
Helper functions, validators, and logging
"""

from .validators import (
    validate_email,
    validate_password_strength,
    validate_username,
    validate_message,
    sanitize_html,
    is_valid_uuid
)
from .helpers import (
    generate_token,
    get_client_ip,
    get_user_agent,
    format_datetime,
    truncate_string,
    safe_filename,
    random_string
)
from .logger import (
    setup_logging,
    get_logger,
    log_request,
    log_error,
    log_info,
    log_warning,
    log_debug
)

__all__ = [
    'validate_email',
    'validate_password_strength',
    'validate_username',
    'validate_message',
    'sanitize_html',
    'is_valid_uuid',
    'generate_token',
    'get_client_ip',
    'get_user_agent',
    'format_datetime',
    'truncate_string',
    'safe_filename',
    'random_string',
    'setup_logging',
    'get_logger',
    'log_request',
    'log_error',
    'log_info',
    'log_warning',
    'log_debug'
]