# backend/reset_admin_password.py
import os
from dotenv import load_dotenv
from app import create_app
from extensions import db
from models import User
from flask_bcrypt import Bcrypt

def reset_admin_password():
    """Reset admin password"""
    load_dotenv()
    app = create_app()
    bcrypt = Bcrypt()
    
    with app.app_context():
        # Find admin user
        admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("❌ Admin user not found!")
            return
        
        # Set new password - CHANGE THIS!
        new_password = 'Admin@2026!'
        
        # Hash the new password
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        # Update user
        admin.password_hash = hashed_password
        admin.is_admin = True
        admin.is_verified = True
        admin.is_active = True
        
        db.session.commit()
        
        print("=" * 60)
        print("✅ Admin password reset successfully!")
        print("=" * 60)
        print(f"   Username: {admin.username}")
        print(f"   Email: {admin.email}")
        print(f"   New Password: {new_password}")
        print(f"   Admin: {admin.is_admin}")
        print(f"   Verified: {admin.is_verified}")
        print("=" * 60)
        print("⚠️  Please change the password immediately after first login!")
        print("=" * 60)

if __name__ == '__main__':
    reset_admin_password()