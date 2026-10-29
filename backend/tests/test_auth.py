# backend/tests/test_auth.py
import pytest
import json
from unittest.mock import patch
from models import User, LoginHistory, UserSession
from services.auth_service import AuthService
from . import BaseTestCase

class TestAuth(BaseTestCase):
    """Test authentication endpoints and services"""
    
    def test_register_success(self):
        """Test successful user registration"""
        response = self.client.post('/api/auth/register', json={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'Test@1234',
            'full_name': 'New User'
        })
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'User registered successfully')
        self.assertIn('user', data)
        
        # Verify user was created in database
        user = User.query.filter_by(username='newuser').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'newuser@example.com')
        self.assertEqual(user.full_name, 'New User')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
    
    def test_register_duplicate_username(self):
        """Test registration with duplicate username"""
        # Create first user
        self.create_test_user(username='duplicate')
        
        # Try to create second user with same username
        response = self.client.post('/api/auth/register', json={
            'username': 'duplicate',
            'email': 'different@example.com',
            'password': 'Test@1234'
        })
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Username already exists')
    
    def test_register_duplicate_email(self):
        """Test registration with duplicate email"""
        # Create first user
        self.create_test_user(email='duplicate@example.com')
        
        # Try to create second user with same email
        response = self.client.post('/api/auth/register', json={
            'username': 'different',
            'email': 'duplicate@example.com',
            'password': 'Test@1234'
        })
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Email already exists')
    
    def test_register_weak_password(self):
        """Test registration with weak password"""
        response = self.client.post('/api/auth/register', json={
            'username': 'weakuser',
            'email': 'weak@example.com',
            'password': '123456'  # Weak password
        })
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)
    
    def test_register_invalid_email(self):
        """Test registration with invalid email"""
        response = self.client.post('/api/auth/register', json={
            'username': 'invaliduser',
            'email': 'invalid-email',
            'password': 'Test@1234'
        })
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Invalid email format')
    
    def test_login_success(self):
        """Test successful login"""
        # Create user
        self.create_test_user(username='loginuser', password='Test@123')
        
        # Login
        response = self.client.post('/api/auth/login', json={
            'identifier': 'loginuser',
            'password': 'Test@123'
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Login successful')
        self.assertIn('access_token', data)
        self.assertIn('refresh_token', data)
        self.assertIn('user', data)
        
        # Verify session was created
        session = UserSession.query.filter_by(user_id=data['user']['id']).first()
        self.assertIsNotNone(session)
        self.assertTrue(session.is_active)
    
    def test_login_with_email(self):
        """Test login with email instead of username"""
        # Create user
        self.create_test_user(username='emailuser', email='email@example.com', password='Test@123')
        
        # Login with email
        response = self.client.post('/api/auth/login', json={
            'identifier': 'email@example.com',
            'password': 'Test@123'
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Login successful')
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        # Create user
        self.create_test_user(username='invaliduser', password='Test@123')
        
        # Wrong password
        response = self.client.post('/api/auth/login', json={
            'identifier': 'invaliduser',
            'password': 'WrongPassword'
        })
        
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Invalid credentials')
        
        # Non-existent user
        response = self.client.post('/api/auth/login', json={
            'identifier': 'nonexistent',
            'password': 'Test@123'
        })
        
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Invalid credentials')
    
    def test_login_rate_limiting(self):
        """Test rate limiting on login"""
        # Create user
        self.create_test_user(username='ratelimituser', password='Test@123')
        
        # Make multiple failed login attempts
        for i in range(6):  # 6 attempts (limit is 5 per minute)
            response = self.client.post('/api/auth/login', json={
                'identifier': 'ratelimituser',
                'password': 'WrongPassword'
            })
            
            if i < 5:
                self.assertEqual(response.status_code, 401)
            else:
                self.assertEqual(response.status_code, 429)
                data = json.loads(response.data)
                self.assertEqual(data['error'], 'Too many failed attempts. Please try again later.')
    
    def test_logout_success(self):
        """Test successful logout"""
        # Create and login user
        user, token = self.create_test_user()
        
        # Logout
        response = self.client.post('/api/auth/logout',
            headers=self.get_auth_headers(token))
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Logout successful')
        
        # Verify session was deactivated
        session = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
        self.assertIsNone(session)
        
        # Verify user status updated
        user = User.query.get(user.id)
        self.assertEqual(user.online_status, 'offline')
    
    def test_refresh_token(self):
        """Test token refresh"""
        # Create and login user
        user, token = self.create_test_user()
        
        # Login again to get refresh token
        login_response = self.client.post('/api/auth/login', json={
            'identifier': 'testuser',
            'password': 'Test@123'
        })
        login_data = json.loads(login_response.data)
        refresh_token = login_data.get('refresh_token')
        
        # Refresh token
        response = self.client.post('/api/auth/refresh',
            headers={
                'Authorization': f'Bearer {refresh_token}',
                'Content-Type': 'application/json'
            })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Token refreshed successfully')
    
    def test_change_password_success(self):
        """Test successful password change"""
        # Create and login user
        user, token = self.create_test_user()
        
        # Change password
        response = self.client.post('/api/auth/change-password',
            headers=self.get_auth_headers(token),
            json={
                'old_password': 'Test@123',
                'new_password': 'NewTest@123'
            })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Password changed successfully')
        
        # Verify can login with new password
        login_response = self.client.post('/api/auth/login', json={
            'identifier': 'testuser',
            'password': 'NewTest@123'
        })
        self.assertEqual(login_response.status_code, 200)
    
    def test_change_password_wrong_old(self):
        """Test password change with wrong old password"""
        # Create and login user
        user, token = self.create_test_user()
        
        # Change password with wrong old password
        response = self.client.post('/api/auth/change-password',
            headers=self.get_auth_headers(token),
            json={
                'old_password': 'WrongPassword',
                'new_password': 'NewTest@123'
            })
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Current password is incorrect')
    
    def test_forgot_password(self):
        """Test forgot password request"""
        # Create user
        self.create_test_user(username='forgotuser', email='forgot@example.com')
        
        # Request password reset
        response = self.client.post('/api/auth/forgot-password', json={
            'email': 'forgot@example.com'
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'If the email exists, a reset link will be sent')
    
    def test_forgot_password_non_existent_email(self):
        """Test forgot password with non-existent email"""
        response = self.client.post('/api/auth/forgot-password', json={
            'email': 'nonexistent@example.com'
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'If the email exists, a reset link will be sent')