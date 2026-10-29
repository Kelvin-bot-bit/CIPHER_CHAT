# backend/services/crypto_service.py
import os
import base64
import hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
import json
from typing import Tuple, Dict, Optional

class CryptoService:
    """Handles all cryptographic operations for the application"""
    
    @staticmethod
    def generate_rsa_key_pair(key_size: int = 2048) -> Tuple[str, str]:
        """
        Generate RSA key pair
        
        Args:
            key_size: Size of RSA key in bits (default: 2048)
        
        Returns:
            Tuple of (public_key_pem, private_key_pem)
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        
        # Serialize public key
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Serialize private key (without encryption - will be encrypted separately)
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        return public_key_pem.decode('utf-8'), private_key_pem.decode('utf-8')
    
    @staticmethod
    def encrypt_private_key_with_password(private_key_pem: str, password: str) -> str:
        """
        Encrypt a private key with a password using PBKDF2 and AES
        
        Args:
            private_key_pem: Private key in PEM format
            password: User's password
        
        Returns:
            Encrypted private key as base64 string
        """
        # Generate salt
        salt = os.urandom(32)
        
        # Derive key from password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        
        # Encrypt private key with AES-GCM
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        
        encrypted_data = aesgcm.encrypt(
            nonce,
            private_key_pem.encode('utf-8'),
            None
        )
        
        # Combine salt + nonce + encrypted data
        combined = salt + nonce + encrypted_data
        return base64.b64encode(combined).decode('utf-8')
    
    @staticmethod
    def decrypt_private_key_with_password(encrypted_data_b64: str, password: str) -> str:
        """
        Decrypt a private key using password
        
        Args:
            encrypted_data_b64: Base64 encoded encrypted data
            password: User's password
        
        Returns:
            Decrypted private key in PEM format
        """
        combined = base64.b64decode(encrypted_data_b64)
        
        # Extract components
        salt = combined[:32]
        nonce = combined[32:44]
        encrypted_key = combined[44:]
        
        # Derive key from password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        
        # Decrypt
        aesgcm = AESGCM(key)
        decrypted_data = aesgcm.decrypt(nonce, encrypted_key, None)
        
        return decrypted_data.decode('utf-8')
    
    @staticmethod
    def encrypt_message(
        plaintext: str,
        recipient_public_key_pem: str,
        sender_private_key_pem: str
    ) -> Dict[str, str]:
        """
        Encrypt a message with E2EE
        
        Args:
            plaintext: Message to encrypt
            recipient_public_key_pem: Recipient's RSA public key
            sender_private_key_pem: Sender's RSA private key for signing
        
        Returns:
            Dictionary with encrypted message, AES key, nonce, tag, signature
        """
        try:
            # 1. Generate random AES key (256-bit)
            aes_key = os.urandom(32)
            
            # 2. Generate random nonce (12 bytes for AES-GCM)
            nonce = os.urandom(12)
            
            # 3. Encrypt the message using AES-256-GCM
            aesgcm = AESGCM(aes_key)
            encrypted_message = aesgcm.encrypt(
                nonce,
                plaintext.encode('utf-8'),
                None
            )
            
            # 4. Load recipient's RSA public key
            recipient_public_key = serialization.load_pem_public_key(
                recipient_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            
            # 5. Encrypt the AES key using recipient's RSA public key
            encrypted_aes_key = recipient_public_key.encrypt(
                aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # 6. Load sender's RSA private key
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_pem.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            
            # 7. Sign the encrypted message using sender's private key
            signature = sender_private_key.sign(
                encrypted_message,
                padding.PSS(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # 8. Generate a tag from the encrypted message (16 bytes)
            # Using SHA-256 hash and taking first 16 bytes as tag
            tag_hash = hashlib.sha256(encrypted_message).digest()
            tag = tag_hash[:16]
            
            # 9. Return all encrypted components as base64
            return {
                'encrypted_message': base64.b64encode(encrypted_message).decode('utf-8'),
                'encrypted_aes_key': base64.b64encode(encrypted_aes_key).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'tag': base64.b64encode(tag).decode('utf-8'),
                'signature': base64.b64encode(signature).decode('utf-8')
            }
        except Exception as e:
            print(f"Encryption error: {e}")
            raise
    
    @staticmethod
    def encrypt_message_dual(
        plaintext: str,
        recipient_public_key_pem: str,
        sender_public_key_pem: str,
        sender_private_key_pem: str
    ) -> Dict[str, str]:
        """
        Same as encrypt_message, but wraps the AES content key twice — once
        for the recipient's public key (as before) and once for the
        sender's own public key. Without the second copy, the sender's own
        private key can never unwrap a key that was only ever encrypted for
        the recipient, so a sender re-opening their own conversation later
        would see nothing but decrypt failures for everything they sent.

        Returns the same fields as encrypt_message, plus
        encrypted_aes_key_sender.
        """
        try:
            aes_key = os.urandom(32)
            nonce = os.urandom(12)

            aesgcm = AESGCM(aes_key)
            encrypted_message = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

            recipient_public_key = serialization.load_pem_public_key(
                recipient_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            oaep_padding = padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
            encrypted_aes_key = recipient_public_key.encrypt(aes_key, oaep_padding)

            sender_public_key = serialization.load_pem_public_key(
                sender_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            encrypted_aes_key_sender = sender_public_key.encrypt(aes_key, oaep_padding)

            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_pem.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            signature = sender_private_key.sign(
                encrypted_message,
                padding.PSS(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )

            tag_hash = hashlib.sha256(encrypted_message).digest()
            tag = tag_hash[:16]

            return {
                'encrypted_message': base64.b64encode(encrypted_message).decode('utf-8'),
                'encrypted_aes_key': base64.b64encode(encrypted_aes_key).decode('utf-8'),
                'encrypted_aes_key_sender': base64.b64encode(encrypted_aes_key_sender).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'tag': base64.b64encode(tag).decode('utf-8'),
                'signature': base64.b64encode(signature).decode('utf-8')
            }
        except Exception as e:
            print(f"Dual encryption error: {e}")
            raise
    
    @staticmethod
    def decrypt_message(
        encrypted_data: Dict[str, str],
        recipient_private_key_pem: str,
        sender_public_key_pem: str
    ) -> Dict[str, any]:
        """
        Decrypt a received message
        
        Args:
            encrypted_data: Dictionary with encrypted components
            recipient_private_key_pem: Recipient's RSA private key
            sender_public_key_pem: Sender's RSA public key for verification
        
        Returns:
            Dictionary with decrypted message and verification status
        """
        try:
            # 1. Decode base64 data
            encrypted_message = base64.b64decode(encrypted_data['encrypted_message'])
            encrypted_aes_key = base64.b64decode(encrypted_data['encrypted_aes_key'])
            nonce = base64.b64decode(encrypted_data['nonce'])
            signature = base64.b64decode(encrypted_data['signature'])
            
            # 2. Load recipient's RSA private key
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_pem.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            
            # 3. Decrypt the AES key using recipient's RSA private key
            aes_key = recipient_private_key.decrypt(
                encrypted_aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # 4. Decrypt the message using AES-256-GCM
            aesgcm = AESGCM(aes_key)
            decrypted_message = aesgcm.decrypt(nonce, encrypted_message, None)
            
            # 5. Verify the digital signature
            sender_public_key = serialization.load_pem_public_key(
                sender_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            
            try:
                sender_public_key.verify(
                    signature,
                    encrypted_message,
                    padding.PSS(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
                is_valid_signature = True
            except InvalidSignature:
                is_valid_signature = False
            
            return {
                'decrypted_message': decrypted_message.decode('utf-8'),
                'is_valid_signature': is_valid_signature
            }
            
        except Exception as e:
            return {
                'decrypted_message': None,
                'is_valid_signature': False,
                'error': str(e)
            }
    
    @staticmethod
    def encrypt_file(file_data: bytes) -> Dict[str, any]:
        """
        Encrypt a file using AES-256-GCM
        
        Args:
            file_data: File data as bytes
        
        Returns:
            Dictionary with encrypted data and encryption metadata
        """
        # Generate AES key
        aes_key = os.urandom(32)
        
        # Generate nonce
        nonce = os.urandom(12)
        
        # Encrypt file
        aesgcm = AESGCM(aes_key)
        encrypted_data = aesgcm.encrypt(nonce, file_data, None)
        
        # Generate tag
        tag_hash = hashlib.sha256(encrypted_data).digest()
        tag = tag_hash[:16]
        
        return {
            'encrypted_data': encrypted_data,
            'encryption_key': base64.b64encode(aes_key).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8')
        }
    
    @staticmethod
    def decrypt_file(
        encrypted_data: bytes,
        encryption_key_b64: str,
        nonce_b64: str
    ) -> bytes:
        """
        Decrypt a file using AES-256-GCM
        
        Args:
            encrypted_data: Encrypted file data
            encryption_key_b64: Base64 encoded AES key
            nonce_b64: Base64 encoded nonce
        
        Returns:
            Decrypted file data as bytes
        """
        aes_key = base64.b64decode(encryption_key_b64)
        nonce = base64.b64decode(nonce_b64)
        
        aesgcm = AESGCM(aes_key)
        decrypted_data = aesgcm.decrypt(nonce, encrypted_data, None)
        
        return decrypted_data
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using PBKDF2
        
        Args:
            password: Plain text password
        
        Returns:
            Hashed password with salt
        """
        salt = os.urandom(32)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        
        # Store salt + key as base64
        combined = salt + key
        return base64.b64encode(combined).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash
        
        Args:
            password: Plain text password to verify
            hashed_password: Stored hashed password
        
        Returns:
            True if password matches, False otherwise
        """
        combined = base64.b64decode(hashed_password)
        salt = combined[:32]
        stored_key = combined[32:]
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        
        return key == stored_key
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        Generate a secure random token
        
        Args:
            length: Length of token in bytes
        
        Returns:
            Base64 encoded token
        """
        return base64.b64encode(os.urandom(length)).decode('utf-8')
    
    @staticmethod
    def compute_file_hash(file_data: bytes) -> str:
        """
        Compute SHA-256 hash of file data
        
        Args:
            file_data: File data as bytes
        
        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        sha256_hash.update(file_data)
        return sha256_hash.hexdigest()
    
    @staticmethod
    def encrypt_group_key(
        group_key: bytes,
        member_public_key_pem: str
    ) -> str:
        """
        Encrypt a group key for a specific member
        
        Args:
            group_key: Group encryption key
            member_public_key_pem: Member's RSA public key
        
        Returns:
            Base64 encrypted group key
        """
        public_key = serialization.load_pem_public_key(
            member_public_key_pem.encode('utf-8'),
            backend=default_backend()
        )
        
        encrypted_key = public_key.encrypt(
            group_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return base64.b64encode(encrypted_key).decode('utf-8')
    
    @staticmethod
    def decrypt_group_key(
        encrypted_key_b64: str,
        member_private_key_pem: str
    ) -> bytes:
        """
        Decrypt a group key for a member
        
        Args:
            encrypted_key_b64: Base64 encrypted group key
            member_private_key_pem: Member's RSA private key
        
        Returns:
            Decrypted group key as bytes
        """
        private_key = serialization.load_pem_private_key(
            member_private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        group_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return group_key

    @staticmethod
    def encrypt_with_raw_key(
        plaintext: str,
        raw_aes_key: bytes,
        sender_private_key_pem: str
    ) -> Dict[str, str]:
        """
        Encrypt a message using an AES key the caller already has in hand
        (a group's shared content key), rather than generating a fresh one
        and RSA-wrapping it for a single recipient. Used for group messages:
        every member already holds their own RSA-wrapped copy of this same
        key via GroupMember.encrypted_group_key, so there's no need to wrap
        it again per-message the way a 1:1 message wraps a fresh key for
        its one recipient.

        Args:
            plaintext: Message to encrypt
            raw_aes_key: The group's raw 256-bit AES key
            sender_private_key_pem: Sender's RSA private key for signing

        Returns:
            Dictionary with encrypted message, nonce, tag, signature.
            No encrypted_aes_key — callers should store the sender's own
            encrypted_group_key alongside this for reference, not a fresh
            per-message wrap.
        """
        try:
            nonce = os.urandom(12)
            aesgcm = AESGCM(raw_aes_key)
            encrypted_message = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_pem.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            signature = sender_private_key.sign(
                encrypted_message,
                padding.PSS(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )

            tag_hash = hashlib.sha256(encrypted_message).digest()
            tag = tag_hash[:16]

            return {
                'encrypted_message': base64.b64encode(encrypted_message).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'tag': base64.b64encode(tag).decode('utf-8'),
                'signature': base64.b64encode(signature).decode('utf-8')
            }
        except Exception as e:
            print(f"Group encryption error: {e}")
            raise

    @staticmethod
    def decrypt_with_raw_key(
        encrypted_data: Dict[str, str],
        raw_aes_key: bytes,
        sender_public_key_pem: str
    ) -> Dict[str, any]:
        """
        Decrypt a group message using the group's raw AES key (obtained by
        the caller via decrypt_group_key on the viewer's own
        encrypted_group_key), and verify it against the sender's signature.

        Args:
            encrypted_data: Dict with encrypted_message, nonce, signature
            raw_aes_key: The group's raw 256-bit AES key
            sender_public_key_pem: Sender's RSA public key for verification

        Returns:
            Dictionary with decrypted_message and is_valid_signature
        """
        encrypted_message = base64.b64decode(encrypted_data['encrypted_message'])
        nonce = base64.b64decode(encrypted_data['nonce'])

        is_valid_signature = False
        try:
            sender_public_key = serialization.load_pem_public_key(
                sender_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            signature = base64.b64decode(encrypted_data['signature'])
            sender_public_key.verify(
                signature,
                encrypted_message,
                padding.PSS(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            is_valid_signature = True
        except Exception:
            is_valid_signature = False

        aesgcm = AESGCM(raw_aes_key)
        decrypted_message = aesgcm.decrypt(nonce, encrypted_message, None)

        return {
            'decrypted_message': decrypted_message.decode('utf-8'),
            'is_valid_signature': is_valid_signature
        }

    @staticmethod
    def wrap_key_with_raw_key(raw_key_to_wrap: bytes, wrapping_key: bytes) -> Dict[str, str]:
        """
        Encrypt one AES key with another AES key (AES-GCM key wrapping).
        Used to protect a file/voice-note's content key with a group's
        shared key, so every group member can unwrap it via the same
        mechanism they already use for group messages — without needing
        an RSA operation per member for every uploaded file.
        """
        nonce = os.urandom(12)
        aesgcm = AESGCM(wrapping_key)
        wrapped = aesgcm.encrypt(nonce, raw_key_to_wrap, None)
        return {
            'wrapped_key': base64.b64encode(wrapped).decode('utf-8'),
            'wrap_nonce': base64.b64encode(nonce).decode('utf-8'),
        }

    @staticmethod
    def unwrap_key_with_raw_key(wrapped_key_b64: str, wrap_nonce_b64: str, wrapping_key: bytes) -> bytes:
        """Reverse of wrap_key_with_raw_key."""
        aesgcm = AESGCM(wrapping_key)
        wrapped = base64.b64decode(wrapped_key_b64)
        nonce = base64.b64decode(wrap_nonce_b64)
        return aesgcm.decrypt(nonce, wrapped, None)