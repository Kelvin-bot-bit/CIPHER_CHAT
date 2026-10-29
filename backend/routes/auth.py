# backend/routes/auth.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, 
    create_access_token, create_refresh_token,
    get_jwt, set_access_cookies, set_refresh_cookies,
    unset_jwt_cookies
)
from flask_bcrypt import Bcrypt
from services.auth_service import AuthService
from services.notification_service import NotificationService
from models import User, UserSession
from extensions import db
from middleware.rate_limiter import limiter
from utils.validators import validate_email, validate_password_strength
from datetime import datetime
import logging

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per hour")
def register():
    """
    Register a new user
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - username
            - email
            - password
          properties:
            username:
              type: string
              description: Unique username
            email:
              type: string
              format: email
              description: User's email address
            password:
              type: string
              description: Strong password
            full_name:
              type: string
              description: User's full name
    responses:
      201:
        description: User registered successfully
      400:
        description: Validation error
      429:
        description: Too many requests
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate email
        if not validate_email(data['email']):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate password strength
        password_valid, password_error = validate_password_strength(data['password'])
        if not password_valid:
            return jsonify({'error': password_error}), 400
        
        # Register user
        result = AuthService.register_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            full_name=data.get('full_name')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        # Send verification email (placeholder)
        # Email verification would be implemented here
        
        return jsonify({
            'message': 'User registered successfully',
            'user': result['user']
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Registration failed'}), 500

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """
    Login user and get tokens
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - identifier
            - password
          properties:
            identifier:
              type: string
              description: Username or email
            password:
              type: string
              description: User's password
    responses:
      200:
        description: Login successful
      401:
        description: Invalid credentials
      429:
        description: Too many requests
    """
    try:
        data = request.get_json(silent=True) or {}
        
        if not data.get('identifier') or not data.get('password'):
            if data.get('identifier'):
                from models import LoginHistory
                from utils.request_info import client_ip
                AuthService._record_login_failure(
                    str(data['identifier'])[:255], None, 'invalid_request',
                    'Login request was missing the password', client_ip(), request.headers.get('User-Agent'))
            return jsonify({'error': 'Identifier and password are required'}), 400
        
        # Get client info (X-Forwarded-For is only trusted when configured)
        from utils.request_info import client_ip
        ip_address = client_ip()
        user_agent = request.headers.get('User-Agent')
        
        # Login user
        result = AuthService.login_user(
            identifier=str(data['identifier']),
            password=str(data['password']),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), result.get('status_code', 401)
        
        # Create response with tokens.
        #
        # access_token is included here in addition to being set as an
        # httpOnly cookie: the cookie is what protects HTTP requests from
        # XSS-based theft, but Socket.IO's handshake (see
        # socket_events/presence_events.py) needs the raw token string,
        # which JS can never read out of an httpOnly cookie. Exposing it
        # here — once, right after a real password check — is what lets a
        # legitimate client hand it to the socket connection without
        # weakening the cookie itself.
        response = jsonify({
            'message': 'Login successful',
            'user': result['user'],
            'session_id': result.get('session_id'),
            'access_token': result['access_token']
        })
        
        # Set JWT cookies
        set_access_cookies(response, result['access_token'])
        set_refresh_cookies(response, result['refresh_token'])
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Login failed'}), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout user
    ---
    tags:
      - Authentication
    responses:
      200:
        description: Logout successful
    """
    try:
        user_id = int(get_jwt_identity())
        session_id = request.json.get('session_id') if request.json else None
        
        # Logout user
        AuthService.logout_user(user_id, session_id)
        
        # Clear cookies
        response = jsonify({'message': 'Logout successful'})
        unset_jwt_cookies(response)
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({'error': 'Logout failed'}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token
    ---
    tags:
      - Authentication
    responses:
      200:
        description: Token refreshed successfully
      401:
        description: Invalid refresh token
    """
    try:
        user_id = int(get_jwt_identity())
        # The refresh flow runs on the httpOnly refresh cookie, not an
        # Authorization header — reading from the header (as this did
        # before) meant `refresh_token` was always an empty string here,
        # so AuthService.refresh_token() could never find a matching
        # session and this endpoint effectively never worked over cookies.
        refresh_cookie_name = current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token_cookie')
        refresh_token = request.cookies.get(refresh_cookie_name, '')
        
        result = AuthService.refresh_token(refresh_token)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 401
        
        # See the comment in login() — the raw token is exposed here too so
        # a client whose in-memory copy expired (e.g. a socket reconnecting
        # after the access token's 1-hour lifetime) can pick up a fresh one
        # without the user having to log in again.
        response = jsonify({
            'message': 'Token refreshed successfully',
            'access_token': result['access_token']
        })
        
        set_access_cookies(response, result['access_token'])
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({'error': 'Token refresh failed'}), 500

@auth_bp.route('/verify-email/<int:user_id>', methods=['GET'])
def verify_email(user_id):
    """
    Verify user's email
    ---
    tags:
      - Authentication
    parameters:
      - name: user_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Email verified successfully
      404:
        description: User not found
    """
    try:
        result = AuthService.verify_email(user_id)
        
        if not result:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'message': 'Email verified successfully'}), 200
        
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}")
        return jsonify({'error': 'Email verification failed'}), 500

@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """
    Change user's password
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - old_password
            - new_password
          properties:
            old_password:
              type: string
            new_password:
              type: string
    responses:
      200:
        description: Password changed successfully
      400:
        description: Validation error
      401:
        description: Invalid credentials
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data.get('old_password') or not data.get('new_password'):
            return jsonify({'error': 'Old and new passwords are required'}), 400
        
        # Validate new password
        password_valid, password_error = validate_password_strength(data['new_password'])
        if not password_valid:
            return jsonify({'error': password_error}), 400
        
        result = AuthService.change_password(
            user_id,
            data['old_password'],
            data['new_password']
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        logger.error(f"Password change error: {str(e)}")
        return jsonify({'error': 'Password change failed'}), 500

@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    """
    Request password reset
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
          properties:
            email:
              type: string
              format: email
    responses:
      200:
        description: Password reset email sent
      404:
        description: Email not found
    """
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Find user by email
        user = User.query.filter_by(email=email.lower()).first()
        if not user:
            # Don't reveal if email exists or not
            return jsonify({'message': 'If the email exists, a reset link will be sent'}), 200
        
        # Generate password reset token (implement this)
        # This would typically involve creating a JWT with short expiration
        
        # Send reset email (placeholder)
        # EmailService.send_password_reset_email(user.email, reset_token)
        
        return jsonify({'message': 'Password reset link sent to your email'}), 200
        
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        return jsonify({'error': 'Password reset request failed'}), 500

@auth_bp.route('/reset-password', methods=['POST'])
@limiter.limit("3 per hour")
def reset_password():
    """
    Reset password with token
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - token
            - new_password
          properties:
            token:
              type: string
            new_password:
              type: string
    responses:
      200:
        description: Password reset successful
      400:
        description: Invalid token or password
    """
    try:
        data = request.get_json()
        token = data.get('token')
        new_password = data.get('new_password')
        
        if not token or not new_password:
            return jsonify({'error': 'Token and new password are required'}), 400
        
        # Validate password
        password_valid, password_error = validate_password_strength(new_password)
        if not password_valid:
            return jsonify({'error': password_error}), 400
        
        # Verify token and reset password (implement this)
        # This would verify the JWT token and reset the password
        
        return jsonify({'message': 'Password reset successful'}), 200
        
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}")
        return jsonify({'error': 'Password reset failed'}), 500