# backend/tests/test_crypto.py
import pytest
import json
import base64
from services.crypto_service import CryptoService
from services.key_management import KeyManagementService
from . import BaseTestCase

class TestCrypto(BaseTestCase):
    """Test cryptographic operations"""
    
    def test_rsa_key_generation(self):
        """Test RSA key pair generation"""
        public_key, private_key = CryptoService.generate_rsa_key_pair()
        
        self.assertIsNotNone(public_key)
        self.assertIsNotNone(private_key)
        self.assertIn('BEGIN PUBLIC KEY', public_key)
        self.assertIn('BEGIN PRIVATE KEY', private_key)
    
    def test_encrypt_decrypt_private_key(self):
        """Test encrypting and decrypting private key with password"""
        # Generate RSA key pair
        public_key, private_key = CryptoService.generate_rsa_key_pair()
        
        # Encrypt private key
        password = 'Test@123'
        encrypted = CryptoService.encrypt_private_key_with_password(private_key, password)
        
        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, private_key)
        
        # Decrypt private key
        decrypted = CryptoService.decrypt_private_key_with_password(encrypted, password)
        
        self.assertEqual(decrypted, private_key)
    
    def test_encrypt_decrypt_private_key_wrong_password(self):
        """Test decrypting private key with wrong password"""
        # Generate RSA key pair
        public_key, private_key = CryptoService.generate_rsa_key_pair()
        
        # Encrypt private key
        encrypted = CryptoService.encrypt_private_key_with_password(private_key, 'Test@123')
        
        # Decrypt with wrong password
        with pytest.raises(Exception):
            CryptoService.decrypt_private_key_with_password(encrypted, 'WrongPassword')
    
    def test_encrypt_decrypt_message(self):
        """Test encrypting and decrypting a message"""
        # Generate key pairs for sender and recipient
        sender_public, sender_private = CryptoService.generate_rsa_key_pair()
        recipient_public, recipient_private = CryptoService.generate_rsa_key_pair()
        
        # Message to encrypt
        original_message = "Hello, this is a secret message!"
        
        # Encrypt message
        encrypted_data = CryptoService.encrypt_message(
            original_message,
            recipient_public,
            sender_private
        )
        
        self.assertIsNotNone(encrypted_data)
        self.assertIn('encrypted_message', encrypted_data)
        self.assertIn('encrypted_aes_key', encrypted_data)
        self.assertIn('nonce', encrypted_data)
        self.assertIn('signature', encrypted_data)
        
        # Decrypt message
        decrypted_data = CryptoService.decrypt_message(
            encrypted_data,
            recipient_private,
            sender_public
        )
        
        self.assertEqual(decrypted_data['decrypted_message'], original_message)
        self.assertTrue(decrypted_data['is_valid_signature'])
    
    def test_encrypt_decrypt_message_tampered(self):
        """Test decrypting a tampered message"""
        # Generate key pairs
        sender_public, sender_private = CryptoService.generate_rsa_key_pair()
        recipient_public, recipient_private = CryptoService.generate_rsa_key_pair()
        
        # Encrypt message
        encrypted_data = CryptoService.encrypt_message(
            "Original message",
            recipient_public,
            sender_private
        )
        
        # Tamper with the message
        encrypted_data['encrypted_message'] = 'tampered_data'
        
        # Try to decrypt
        decrypted_data = CryptoService.decrypt_message(
            encrypted_data,
            recipient_private,
            sender_public
        )
        
        self.assertFalse(decrypted_data['is_valid_signature'])
    
    def test_encrypt_decrypt_file(self):
        """Test encrypting and decrypting a file"""
        # Sample file data
        file_data = b"This is a test file content"
        
        # Encrypt file
        encrypted_result = CryptoService.encrypt_file(file_data)
        
        self.assertIsNotNone(encrypted_result)
        self.assertIn('encrypted_data', encrypted_result)
        self.assertIn('encryption_key', encrypted_result)
        self.assertIn('nonce', encrypted_result)
        
        # Decrypt file
        decrypted_data = CryptoService.decrypt_file(
            encrypted_result['encrypted_data'],
            encrypted_result['encryption_key'],
            encrypted_result['nonce']
        )
        
        self.assertEqual(decrypted_data, file_data)
    
    def test_password_hashing(self):
        """Test password hashing and verification"""
        password = "Test@123"
        
        # Hash password
        hashed = CryptoService.hash_password(password)
        
        self.assertIsNotNone(hashed)
        self.assertNotEqual(hashed, password)
        
        # Verify password
        self.assertTrue(CryptoService.verify_password(password, hashed))
        self.assertFalse(CryptoService.verify_password('WrongPassword', hashed))
    
    def test_generate_secure_token(self):
        """Test secure token generation"""
        token1 = CryptoService.generate_secure_token(32)
        token2 = CryptoService.generate_secure_token(32)
        
        self.assertIsNotNone(token1)
        self.assertIsNotNone(token2)
        self.assertNotEqual(token1, token2)
        self.assertEqual(len(base64.b64decode(token1)), 32)
    
    def test_compute_file_hash(self):
        """Test file hash computation"""
        file_data = b"Test file content"
        
        hash1 = CryptoService.compute_file_hash(file_data)
        hash2 = CryptoService.compute_file_hash(b"Different content")
        
        self.assertIsNotNone(hash1)
        self.assertEqual(len(hash1), 64)  # SHA-256 produces 64 hex characters
        self.assertNotEqual(hash1, hash2)
        
        # Same data should produce same hash
        hash3 = CryptoService.compute_file_hash(b"Test file content")
        self.assertEqual(hash1, hash3)
    
    def test_encrypt_group_key(self):
        """Test group key encryption and decryption"""
        # Generate keys for two members
        member1_public, member1_private = CryptoService.generate_rsa_key_pair()
        member2_public, member2_private = CryptoService.generate_rsa_key_pair()
        
        # Group key
        group_key = b"GroupKey1234567890"
        
        # Encrypt for each member
        encrypted_for_1 = CryptoService.encrypt_group_key(group_key, member1_public)
        encrypted_for_2 = CryptoService.encrypt_group_key(group_key, member2_public)
        
        self.assertIsNotNone(encrypted_for_1)
        self.assertIsNotNone(encrypted_for_2)
        self.assertNotEqual(encrypted_for_1, encrypted_for_2)
        
        # Decrypt for each member
        decrypted_1 = CryptoService.decrypt_group_key(encrypted_for_1, member1_private)
        decrypted_2 = CryptoService.decrypt_group_key(encrypted_for_2, member2_private)
        
        self.assertEqual(decrypted_1, group_key)
        self.assertEqual(decrypted_2, group_key)