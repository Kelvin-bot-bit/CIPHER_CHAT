# backend/utils/helpers.py
import secrets
import string
import uuid
from datetime import datetime
from flask import request
import hashlib
import re

def generate_token(length: int = 32) -> str:
    """
    Generate a secure random token
    """
    return secrets.token_urlsafe(length)

def generate_verification_code(length: int = 6) -> str:
    """
    Generate a numeric verification code
    """
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def get_client_ip() -> str:
    """
    Get client IP address from request
    """
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def get_user_agent() -> str:
    """
    Get user agent from request
    """
    return request.headers.get('User-Agent', 'Unknown')

def format_datetime(dt: datetime, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Format datetime object to string
    """
    if dt is None:
        return ''
    return dt.strftime(format_str)

def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    Truncate a string to a maximum length
    """
    if not text:
        return ''
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def safe_filename(filename: str) -> str:
    """
    Generate a safe filename
    """
    # Remove any path components
    filename = filename.replace('/', '').replace('\\', '')
    
    # Generate a random UUID for the filename
    ext = ''
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1]
        if ext:
            ext = f'.{ext}'
    
    return f"{uuid.uuid4().hex}{ext}"

def random_string(length: int = 10) -> str:
    """
    Generate a random string
    """
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def hash_string(text: str, algorithm: str = 'sha256') -> str:
    """
    Hash a string using the specified algorithm
    """
    hash_func = getattr(hashlib, algorithm)
    return hash_func(text.encode('utf-8')).hexdigest()

def extract_mentions(text: str) -> list:
    """
    Extract @mentions from text
    """
    pattern = r'@([a-zA-Z0-9_]+)'
    return re.findall(pattern, text)

def extract_hashtags(text: str) -> list:
    """
    Extract #hashtags from text
    """
    pattern = r'#([a-zA-Z0-9_]+)'
    return re.findall(pattern, text)

def format_phone_number(phone: str) -> str:
    """
    Format phone number
    """
    # Remove non-digit characters
    phone = re.sub(r'\D', '', phone)
    
    if len(phone) == 10:
        return f'({phone[:3]}) {phone[3:6]}-{phone[6:]}'
    elif len(phone) == 11:
        return f'+{phone[0]} ({phone[1:4]}) {phone[4:7]}-{phone[7:]}'
    
    return phone

def get_file_extension(filename: str) -> str:
    """
    Get file extension
    """
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()

def is_valid_json(json_str: str) -> bool:
    """
    Check if a string is valid JSON
    """
    import json
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

def clean_text(text: str) -> str:
    """
    Clean text by removing extra whitespace and special characters
    """
    if not text:
        return ''
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Remove special characters (keep alphanumeric, spaces, and basic punctuation)
    text = re.sub(r'[^\w\s.,!?@#$%^&*()\-+=]', '', text)
    
    return text

def parse_date(date_str: str, format_str: str = '%Y-%m-%d') -> datetime:
    """
    Parse date string to datetime object
    """
    try:
        return datetime.strptime(date_str, format_str)
    except ValueError:
        return None