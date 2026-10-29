# backend/tests/__init__.py
"""
Test package for Secure Chat Application
Unit and integration tests for all components
"""

import os
import sys
import pytest
from flask import Flask
from flask_testing import TestCase

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db

class BaseTestCase(TestCase):
    """Base test case with common setup and teardown"""
    
    def create_app(self):
        """Create a test app instance"""
        app = create_app('config.TestingConfig')
        return app
    
    def setUp(self):
        """Set up test environment"""
        db.create_all()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
    
    def tearDown(self):
        """Clean up test environment"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def get_auth_headers(self, token):
        """Get authorization headers"""
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def create_test_user(self, username='testuser', email='test@example.com', password='Test@123'):
        """Create a test user and return the user and auth token"""
        from models import User
        from services.auth_service import AuthService
        
        # Register user
        result = AuthService.register_user(
            username=username,
            email=email,
            password=password,
            full_name='Test User'
        )
        
        if result.get('error'):
            return None, None
        
        user = User.query.filter_by(username=username).first()
        
        # Login to get token
        login_result = AuthService.login_user(
            identifier=username,
            password=password
        )
        
        if login_result.get('error'):
            return user, None
        
        return user, login_result.get('access_token')
    
    def get_test_user(self):
        """Get or create a test user"""
        from models import User
        
        user = User.query.filter_by(username='testuser').first()
        if not user:
            user, token = self.create_test_user()
            return user
        
        return user

__all__ = ['BaseTestCase']