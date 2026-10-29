# backend/services/key_management.py
import os
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from models import User, Group, UserDevice
from extensions import db
from .crypto_service import CryptoService

class KeyManagementService:
    """Handles key management operations"""
    
    @staticmethod
    def rotate_user_keys(user_id: int, old_password: str, new_password: str = None) -> dict:
        """
        Rotate a user's RSA key pair
        
        Args:
            user_id: User ID
            old_password: Current password for decryption
            new_password: New password (if changing)
        
        Returns:
            Dictionary with success or error
        """
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        try:
            # Decrypt old private key
            private_key_pem = CryptoService.decrypt_private_key_with_password(
                user.encrypted_private_key,
                old_password
            )
            
            # Generate new key pair
            new_public_key, new_private_key = CryptoService.generate_rsa_key_pair()
            
            # Encrypt new private key
            password_to_use = new_password or old_password
            encrypted_private_key = CryptoService.encrypt_private_key_with_password(
                new_private_key,
                password_to_use
            )
            
            # Update user
            user.public_key = new_public_key
            user.encrypted_private_key = encrypted_private_key
            db.session.commit()
            
            return {
                'success': True,
                'message': 'Keys rotated successfully'
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to rotate keys: {str(e)}'}
    
    @staticmethod
    def generate_group_key(group_id: int, admin_id: int) -> dict:
        """
        Generate a new group key
        
        Args:
            group_id: Group ID
            admin_id: Admin user ID
        
        Returns:
            Dictionary with success or error
        """
        from models import Group, GroupMember
        group = Group.query.get(group_id)
        if not group:
            return {'error': 'Group not found'}
        
        if not group.is_admin(admin_id):
            return {'error': 'Only admins can generate group keys'}
        
        try:
            # Generate new group key
            group_key = os.urandom(32)  # 256-bit AES key
            
            # Encrypt group key for each member
            members = group.get_active_members()
            encrypted_keys = {}
            
            for member in members:
                user = User.query.get(member.user_id)
                if user:
                    encrypted_key = CryptoService.encrypt_group_key(
                        group_key,
                        user.public_key
                    )
                    encrypted_keys[member.user_id] = encrypted_key
            
            # Store group key in a format that can be decrypted by admins
            # We'll store it encrypted with the admin's key
            admin_user = User.query.get(admin_id)
            admin_encrypted_key = CryptoService.encrypt_group_key(
                group_key,
                admin_user.public_key
            )
            
            # Update group
            group.group_key = admin_encrypted_key
            db.session.commit()
            
            return {
                'success': True,
                'message': 'Group key generated successfully',
                'member_keys': encrypted_keys
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to generate group key: {str(e)}'}
    
    @staticmethod
    def get_user_private_key(user_id: int, password: str) -> dict:
        """
        Get a user's decrypted private key
        
        Args:
            user_id: User ID
            password: User's password
        
        Returns:
            Dictionary with private key or error
        """
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        try:
            private_key = CryptoService.decrypt_private_key_with_password(
                user.encrypted_private_key,
                password
            )
            
            return {
                'success': True,
                'private_key': private_key
            }
            
        except Exception as e:
            return {'error': f'Failed to decrypt private key: {str(e)}'}
    
    @staticmethod
    def register_device(user_id: int, device_name: str, device_type: str, password: str) -> dict:
        """
        Register a new device for a user
        
        Args:
            user_id: User ID
            device_name: Name of the device
            device_type: Type of device (mobile, desktop, web)
            password: User's password
        
        Returns:
            Dictionary with device data or error
        """
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        try:
            # Get user's private key
            private_key_result = KeyManagementService.get_user_private_key(user_id, password)
            if not private_key_result.get('success'):
                return {'error': private_key_result.get('error')}
            
            private_key = private_key_result['private_key']
            
            # Generate device-specific key pair
            device_public_key, device_private_key = CryptoService.generate_rsa_key_pair()
            
            # Encrypt device private key with user's key
            # We'll encrypt it with the user's password for storage
            encrypted_device_key = CryptoService.encrypt_private_key_with_password(
                device_private_key,
                password
            )
            
            # Generate unique device ID
            device_id = f"{user_id}_{device_name}_{os.urandom(8).hex()}"
            
            # Create device record
            device = UserDevice(
                user_id=user_id,
                device_id=device_id,
                device_name=device_name,
                device_type=device_type,
                device_public_key=device_public_key,
                device_encrypted_private_key=encrypted_device_key,
                is_active=True
            )
            db.session.add(device)
            db.session.commit()
            
            return {
                'success': True,
                'device': device.to_dict(),
                'device_id': device_id,
                'device_public_key': device_public_key
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to register device: {str(e)}'}
    
    @staticmethod
    def revoke_device(user_id: int, device_id: str) -> dict:
        """
        Revoke a device
        
        Args:
            user_id: User ID
            device_id: Device ID
        
        Returns:
            Dictionary with success or error
        """
        device = UserDevice.query.filter_by(
            user_id=user_id,
            device_id=device_id
        ).first()
        
        if not device:
            return {'error': 'Device not found'}
        
        device.revoke()
        
        return {'success': True}
    
    @staticmethod
    def get_user_devices(user_id: int) -> dict:
        """
        Get all devices for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with devices list
        """
        devices = UserDevice.query.filter_by(
            user_id=user_id
        ).order_by(
            UserDevice.created_at.desc()
        ).all()
        
        return {
            'success': True,
            'devices': [d.to_dict() for d in devices],
            'total': len(devices)
        }
    
    @staticmethod
    def backup_encrypted_keys(user_id: int, password: str) -> dict:
        """
        Backup a user's encrypted keys
        
        Args:
            user_id: User ID
            password: User's password
        
        Returns:
            Dictionary with backup data
        """
        user = User.query.get(user_id)
        if not user:
            return {'error': 'User not found'}
        
        try:
            # Get private key
            private_key = CryptoService.decrypt_private_key_with_password(
                user.encrypted_private_key,
                password
            )
            
            # Create backup
            backup_data = {
                'user_id': user.id,
                'username': user.username,
                'public_key': user.public_key,
                'private_key': private_key,
                'backup_date': datetime.utcnow().isoformat()
            }
            
            # Encrypt backup with a backup key
            backup_key = os.urandom(32)
            encrypted_backup = CryptoService.encrypt_file(
                json.dumps(backup_data).encode('utf-8')
            )
            
            return {
                'success': True,
                'backup_key': base64.b64encode(backup_key).decode('utf-8'),
                'encrypted_backup': {
                    'data': base64.b64encode(encrypted_backup['encrypted_data']).decode('utf-8'),
                    'nonce': encrypted_backup['nonce'],
                    'tag': encrypted_backup['tag']
                }
            }
            
        except Exception as e:
            return {'error': f'Failed to create backup: {str(e)}'}
    
    @staticmethod
    def restore_encrypted_keys(
        user_id: int,
        backup_key: str,
        encrypted_backup: dict
    ) -> dict:
        """
        Restore encrypted keys from backup
        
        Args:
            user_id: User ID
            backup_key: Backup encryption key
            encrypted_backup: Encrypted backup data
        
        Returns:
            Dictionary with success or error
        """
        try:
            # Decrypt backup
            key = base64.b64decode(backup_key)
            nonce = base64.b64decode(encrypted_backup['nonce'])
            encrypted_data = base64.b64decode(encrypted_backup['data'])
            
            # Decrypt with AES-GCM
            aesgcm = AESGCM(key)
            decrypted_data = aesgcm.decrypt(nonce, encrypted_data, None)
            
            backup_data = json.loads(decrypted_data.decode('utf-8'))
            
            # Verify user
            if backup_data['user_id'] != user_id:
                return {'error': 'Backup does not belong to this user'}
            
            # Update user's keys
            user = User.query.get(user_id)
            if not user:
                return {'error': 'User not found'}
            
            user.public_key = backup_data['public_key']
            user.encrypted_private_key = backup_data['private_key']
            db.session.commit()
            
            return {
                'success': True,
                'message': 'Keys restored successfully'
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': f'Failed to restore backup: {str(e)}'}