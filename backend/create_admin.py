# backend/create_admin.py
import os
from dotenv import load_dotenv
from app import create_app
from extensions import db
from models import User
from services.auth_service import AuthService
from services.crypto_service import CryptoService
from flask_bcrypt import Bcrypt

def create_admin_user():
    """Create an admin user with proper credentials"""
    load_dotenv()
    app = create_app()
    bcrypt = Bcrypt()
    
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print(f"✅ Admin user already exists!")
            print(f"   Username: {admin.username}")
            print(f"   Email: {admin.email}")
            print(f"   Admin: {admin.is_admin}")
            return
        
        # Admin credentials - CHANGE THESE!
        username = 'admin'
        email = 'admin@securechat.com'
        password = 'Admin@2026!'  # ← Change this to your desired password
        
        # Hash password
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Generate RSA key pair
        public_key, private_key = CryptoService.generate_rsa_key_pair()
        
        # Encrypt private key
        encrypted_private_key = CryptoService.encrypt_private_key_with_password(
            private_key,
            password
        )
        
        # Create admin user
        admin = User(
            username=username,
            email=email,
            password_hash=password_hash,
            full_name='System Administrator',
            public_key=public_key,
            encrypted_private_key=encrypted_private_key,
            is_verified=True,
            is_admin=True,
            is_active=True
        )
        
        db.session.add(admin)
        db.session.commit()
        
        print("=" * 60)
        print("✅ Admin user created successfully!")
        print("=" * 60)
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Admin: {admin.is_admin}")
        print(f"   Verified: {admin.is_verified}")
        print("=" * 60)
        print("⚠️  Please change the password immediately!")
        print("=" * 60)

if __name__ == '__main__':
    create_admin_user()