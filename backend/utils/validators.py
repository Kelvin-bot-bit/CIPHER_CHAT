# backend/utils/validators.py
import re
import uuid
from typing import Tuple, Optional

def validate_email(email: str) -> bool:
    """
    Validate email format
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """
    Validate password strength
    
    Returns:
        (is_valid, error_message)
    """
    if len(password) < 8:
        return False, 'Password must be at least 8 characters long'
    
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter'
    
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter'
    
    if not re.search(r'\d', password):
        return False, 'Password must contain at least one number'
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, 'Password must contain at least one special character'
    
    return True, None

def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Validate username
    """
    if not username or len(username) < 3:
        return False, 'Username must be at least 3 characters long'
    
    if len(username) > 50:
        return False, 'Username must be less than 50 characters'
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, 'Username can only contain letters, numbers, and underscores'
    
    return True, None

def validate_message(message: str, max_length: int = 10000) -> Tuple[bool, Optional[str]]:
    """
    Validate message content
    """
    if not message:
        return False, 'Message cannot be empty'
    
    if len(message) > max_length:
        return False, f'Message cannot exceed {max_length} characters'
    
    # Check for potential XSS
    if re.search(r'<script', message, re.IGNORECASE):
        return False, 'Message contains invalid content'
    
    return True, None

def sanitize_html(text: str) -> str:
    """
    Sanitize HTML content to prevent XSS
    """
    # Remove script tags and their content
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove other dangerous tags
    dangerous_tags = ['iframe', 'object', 'embed', 'applet', 'form', 'input']
    for tag in dangerous_tags:
        text = re.sub(f'<{tag}.*?>.*?</{tag}>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove event handlers
    text = re.sub(r'on\w+\s*=\s*["\'].*?["\']', '', text, flags=re.IGNORECASE)
    
    # Remove javascript: protocol
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    
    return text

def is_valid_uuid(val: str) -> bool:
    """
    Check if a string is a valid UUID
    """
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def validate_file_type(filename: str, allowed_extensions: list) -> bool:
    """
    Validate file type by extension
    """
    if '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_extensions

def validate_file_size(file_size: int, max_size: int) -> bool:
    """
    Validate file size
    """
    return file_size <= max_size

def validate_url(url: str) -> bool:
    """
    Validate URL format
    """
    pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/]?'
    return bool(re.match(pattern, url))