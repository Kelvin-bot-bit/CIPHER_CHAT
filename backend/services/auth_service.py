# backend/services/auth_service.py
from datetime import datetime, timedelta
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token
from flask_bcrypt import Bcrypt
from models import User, UserSession, LoginHistory, AuditLog
from extensions import db
from .key_management import KeyManagementService
from .crypto_service import CryptoService
import re
import os

class AuthService:
    """Handles authentication and authorization operations"""
    
    bcrypt = Bcrypt()
    
    @staticmethod
    def register_user(username: str, email: str, password: str, full_name: str = None) -> dict:
        """
        Register a new user
        
        Args:
            username: Desired username
            email: User's email
            password: User's password
            full_name: User's full name (optional)
        
        Returns:
            Dictionary with user data or error
        """
        # Validate inputs
        validation = AuthService._validate_registration(username, email, password)
        if validation.get('error'):
            return validation
        
        # Check if username or email already exists
        if User.query.filter_by(username=username.lower()).first():
            AuditLog.log_action(user_id=None, action='register_failed', resource_type='user', status='failure',
                                resource_label=username.lower(), actor_email=email.lower(),
                                details={'reason': 'Username already exists'})
            return {'error': 'Username already exists'}
        
        if User.query.filter_by(email=email.lower()).first():
            AuditLog.log_action(user_id=None, action='register_failed', resource_type='user', status='failure',
                                resource_label=username.lower(), actor_email=email.lower(),
                                details={'reason': 'Email already exists'})
            return {'error': 'Email already exists'}
        
        try:
            # Hash password
            password_hash = AuthService.bcrypt.generate_password_hash(password).decode('utf-8')
            
            # Generate RSA key pair
            public_key, private_key = CryptoService.generate_rsa_key_pair()
            
            # Encrypt private key with password
            encrypted_private_key = CryptoService.encrypt_private_key_with_password(
                private_key,
                password
            )
            
            # Auto-verify in development, require verification in production
            is_verified = os.environ.get('FLASK_ENV', 'development') == 'development'
            
            # Create user
            user = User(
                username=username.lower(),
                email=email.lower(),
                password_hash=password_hash,
                full_name=full_name or username,
                public_key=public_key,
                encrypted_private_key=encrypted_private_key,
                is_verified=is_verified,  # Auto-verify in development
                is_active=True
            )
            
            db.session.add(user)
            db.session.commit()
            
            # Log registration
            AuditLog.log_action(
                user_id=user.id,
                action='register',
                resource_type='user',
                resource_id=user.id,
                details={'username': username, 'email': email}
            )
            
            return {
                'success': True,
                'user': user.to_dict(include_private=True)
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Registration failed: {str(e)}'}
    
    # A valid bcrypt hash of a random string. Checked when the account does
    # not exist so "unknown user" and "wrong password" take the same time and
    # cannot be told apart by timing.
    _DUMMY_HASH = None

    @staticmethod
    def _record_login_failure(identifier, user, code, reason, ip_address, user_agent):
        """
        Persist a failed login everywhere it needs to be seen: the login
        history (with a machine-readable code and the human reason), the audit
        trail, the log stream, and the alert rules.
        """
        from utils.useragent import parse_user_agent
        from utils.request_info import current_request_id
        import logging
        try:
            db.session.rollback()
            db.session.add(LoginHistory(
                user_id=user.id if user else None,
                identifier=(identifier or '')[:255] or None,
                login_time=datetime.utcnow(),
                ip_address=ip_address,
                user_agent=user_agent,
                device_type=parse_user_agent(user_agent)['device'],
                success=False,
                failure_code=code,
                failure_reason=reason[:255],
                request_id=current_request_id(),
            ))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logging.getLogger(__name__).error('Could not record failed login: %s', exc)

        AuditLog.log_action(
            user_id=user.id if user else None,
            action='login_failed',
            resource_type='user',
            resource_id=user.id if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            status='failure',
            actor_username=user.username if user else None,
            actor_email=user.email if user else None,
            resource_label=(identifier or '')[:255] or None,
            details={'reason': reason, 'code': code, 'identifier': identifier},
        )
        logging.getLogger('security').warning(
            'Failed login for "%s" from %s: %s', identifier, ip_address, reason,
            extra={'fields': {'category': 'security', 'event': 'login_failed', 'failure_code': code,
                              'identifier': identifier, 'ip': ip_address, 'user_id': user.id if user else None}})

    @staticmethod
    def login_user(identifier: str, password: str, ip_address: str = None, user_agent: str = None) -> dict:
        """
        Log in a user

        Args:
            identifier: Username or email
            password: User's password
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Dictionary with access token and user data, or ``error`` (plus an
            optional ``status_code``). Every failure is recorded with a reason;
            what the *caller* is told stays deliberately vague for wrong
            username / wrong password so accounts cannot be enumerated.
        """
        from flask import current_app
        from utils.useragent import parse_user_agent
        from utils.request_info import current_request_id

        identifier = (identifier or '').strip()
        key = identifier.lower()
        max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
        lockout_minutes = current_app.config.get('LOCKOUT_TIME', 15)
        fail = AuthService._record_login_failure

        # Find user by username or email
        user = User.query.filter(
            (User.username == key) | (User.email == key)
        ).first()

        # Temporary lockout after repeated wrong passwords. Counted per account
        # *and* per typed identifier so guessing non-existent names is limited too.
        recent = LoginHistory.count_recent_failures(
            identifier=key, user_id=user.id if user else None, minutes=lockout_minutes)
        if recent >= max_attempts:
            fail(identifier, user, 'account_locked',
                 f'Locked: {recent} failed attempts in the last {lockout_minutes} minutes',
                 ip_address, user_agent)
            return {'error': f'Too many failed attempts. Please try again in {lockout_minutes} minutes.',
                    'status_code': 429}

        if not user:
            # Burn the same time a real password check would.
            if AuthService._DUMMY_HASH is None:
                AuthService._DUMMY_HASH = AuthService.bcrypt.generate_password_hash(
                    'not-a-real-password').decode('utf-8')
            AuthService.bcrypt.check_password_hash(AuthService._DUMMY_HASH, password or '')
            fail(identifier, None, 'user_not_found',
                 'No account matches this username or email', ip_address, user_agent)
            return {'error': 'Invalid credentials'}

        # Verify password first, so account state is only revealed to someone
        # who actually knows the password.
        if not AuthService.bcrypt.check_password_hash(user.password_hash, password or ''):
            remaining = max_attempts - (recent + 1)
            fail(identifier, user, 'invalid_password',
                 f'Incorrect password (attempt {recent + 1} of {max_attempts})', ip_address, user_agent)
            return {'error': 'Invalid credentials'}

        if not user.is_active:
            fail(identifier, user, 'account_deactivated', 'Account is deactivated', ip_address, user_agent)
            return {'error': 'Account is deactivated'}

        if user.is_suspended:
            fail(identifier, user, 'account_suspended', 'Account is suspended by an administrator',
                 ip_address, user_agent)
            return {'error': 'Account is suspended'}

        # Check if email is verified (skip in development)
        if not user.is_verified:
            if os.environ.get('FLASK_ENV', 'development') == 'development':
                user.is_verified = True
                db.session.commit()
            else:
                fail(identifier, user, 'email_not_verified', 'Email address has not been verified',
                     ip_address, user_agent)
                return {'error': 'Please verify your email address first'}

        try:
            # Generate tokens
            access_token = create_access_token(
                identity=str(user.id),
                expires_delta=timedelta(hours=1)
            )
            refresh_token = create_refresh_token(
                identity=str(user.id),
                expires_delta=timedelta(days=30)
            )

            # Create session
            session = UserSession(
                user_id=user.id,
                access_token=access_token,
                refresh_token=refresh_token,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            db.session.add(session)

            # Log successful login
            login_history = LoginHistory(
                user_id=user.id,
                identifier=identifier[:255] or None,
                login_time=datetime.utcnow(),
                ip_address=ip_address,
                user_agent=user_agent,
                device_type=parse_user_agent(user_agent)['device'],
                success=True,
                request_id=current_request_id(),
            )
            db.session.add(login_history)

            # Update user status
            user.online_status = 'online'
            user.last_seen = datetime.utcnow()

            db.session.commit()

            # Attribute this request (access log, dashboard) to the user who just signed in
            from flask import g, has_request_context
            if has_request_context():
                g.log_user_id = user.id
                g.log_username = user.username

            # Log action
            AuditLog.log_action(
                user_id=user.id,
                action='login',
                resource_type='user',
                resource_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={'success': True, 'identifier': identifier}
            )

            return {
                'success': True,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': user.to_dict(include_private=True),
                'session_id': session.id
            }

        except Exception as e:
            db.session.rollback()
            fail(identifier, user, 'server_error', f'Unexpected error: {str(e)[:150]}', ip_address, user_agent)
            return {'error': f'Login failed: {str(e)}'}

    @staticmethod
    def logout_user(user_id: int, session_id: int = None) -> bool:
        """
        Log out a user
        
        Args:
            user_id: User ID
            session_id: Session ID (optional)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if session_id:
                # Logout specific session
                session = UserSession.query.filter_by(
                    id=session_id,
                    user_id=user_id,
                    is_active=True
                ).first()
                if session:
                    session.is_active = False
            
            # Check if user has any active sessions
            active_sessions = UserSession.query.filter_by(
                user_id=user_id,
                is_active=True
            ).count()
            
            if active_sessions == 0:
                # Update user status to offline
                user = User.query.get(user_id)
                if user:
                    user.online_status = 'offline'
                    user.last_seen = datetime.utcnow()
            
            # Log logout
            login_history = LoginHistory.query.filter_by(
                user_id=user_id,
                logout_time=None
            ).order_by(LoginHistory.login_time.desc()).first()
            
            if login_history:
                login_history.logout_time = datetime.utcnow()
            
            # Audit log
            AuditLog.log_action(
                user_id=user_id,
                action='logout',
                resource_type='user',
                resource_id=user_id
            )
            
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            return False
    
    @staticmethod
    def refresh_token(refresh_token: str) -> dict:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Refresh token
        
        Returns:
            Dictionary with new access token or error
        """
        try:
            # Decode refresh token
            decoded = decode_token(refresh_token)
            user_id = int(decoded['sub'])
            
            # Verify session exists and is active
            session = UserSession.query.filter_by(
                user_id=user_id,
                refresh_token=refresh_token,
                is_active=True
            ).first()
            
            if not session:
                return {'error': 'Invalid or expired refresh token'}
            
            # Generate new access token
            new_access_token = create_access_token(
                identity=str(user_id),
                expires_delta=timedelta(hours=1)
            )
            
            # Update session
            session.access_token = new_access_token
            session.expires_at = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            
            # Audit log
            AuditLog.log_action(
                user_id=user_id,
                action='refresh_token',
                resource_type='session',
                resource_id=session.id
            )
            
            return {
                'success': True,
                'access_token': new_access_token
            }
            
        except Exception as e:
            return {'error': f'Token refresh failed: {str(e)}'}
    
    @staticmethod
    def verify_email(user_id: int) -> bool:
        """
        Verify a user's email address
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful, False otherwise
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return False
            
            user.is_verified = True
            db.session.commit()
            
            AuditLog.log_action(
                user_id=user_id,
                action='verify_email',
                resource_type='user',
                resource_id=user_id,
                details={'verified': True}
            )
            
            return True
            
        except Exception as e:
            db.session.rollback()
            return False
    
    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> dict:
        """
        Change user's password
        
        Args:
            user_id: User ID
            old_password: Current password
            new_password: New password
        
        Returns:
            Dictionary with success or error
        """
        # Validate new password
        validation = AuthService._validate_password(new_password)
        if validation.get('error'):
            return validation
        
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        # Verify old password
        if not AuthService.bcrypt.check_password_hash(user.password_hash, old_password):
            return {'error': 'Current password is incorrect'}
        
        try:
            # Hash new password
            new_password_hash = AuthService.bcrypt.generate_password_hash(new_password).decode('utf-8')
            user.password_hash = new_password_hash
            
            # Re-encrypt private key with new password
            # First decrypt with old password
            private_key = CryptoService.decrypt_private_key_with_password(
                user.encrypted_private_key,
                old_password
            )
            
            # Then re-encrypt with new password
            encrypted_private_key = CryptoService.encrypt_private_key_with_password(
                private_key,
                new_password
            )
            user.encrypted_private_key = encrypted_private_key
            
            db.session.commit()
            
            AuditLog.log_action(
                user_id=user_id,
                action='change_password',
                resource_type='user',
                resource_id=user_id,
                details={'success': True}
            )
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Password change failed: {str(e)}'}
    
    @staticmethod
    def auto_verify_all_users() -> dict:
        """
        Auto-verify all users (for development)
        
        Returns:
            Dictionary with count of verified users
        """
        try:
            users = User.query.filter_by(is_verified=False).all()
            count = len(users)
            
            for user in users:
                user.is_verified = True
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Auto-verified {count} users',
                'count': count
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to auto-verify users: {str(e)}'}
    
    @staticmethod
    def _validate_registration(username: str, email: str, password: str) -> dict:
        """Validate registration input"""
        # Validate username
        if not username or len(username) < 3:
            return {'error': 'Username must be at least 3 characters long'}
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return {'error': 'Username can only contain letters, numbers, and underscores'}
        
        # Validate email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return {'error': 'Invalid email address'}
        
        # Validate password
        password_validation = AuthService._validate_password(password)
        if password_validation.get('error'):
            return password_validation
        
        return {'success': True}
    
    @staticmethod
    def _validate_password(password: str) -> dict:
        """Validate password strength"""
        if len(password) < 8:
            return {'error': 'Password must be at least 8 characters long'}
        if not re.search(r'[A-Z]', password):
            return {'error': 'Password must contain at least one uppercase letter'}
        if not re.search(r'[a-z]', password):
            return {'error': 'Password must contain at least one lowercase letter'}
        if not re.search(r'\d', password):
            return {'error': 'Password must contain at least one number'}
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return {'error': 'Password must contain at least one special character'}
        return {'success': True}