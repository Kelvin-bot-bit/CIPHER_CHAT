# backend/tests/test_models.py
import pytest
from datetime import datetime, timedelta
from models import User, Message, MessageStatus, Friend, FriendRequest, Group, GroupMember
from services.auth_service import AuthService
from . import BaseTestCase

class TestModels(BaseTestCase):
    """Test database models"""
    
    def test_create_user(self):
        """Test user creation"""
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed_password',
            public_key='public_key',
            encrypted_private_key='encrypted_private_key',
            full_name='Test User'
        )
        
        self.app.db.session.add(user)
        self.app.db.session.commit()
        
        retrieved = User.query.filter_by(username='testuser').first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.email, 'test@example.com')
        self.assertEqual(retrieved.full_name, 'Test User')
        self.assertTrue(retrieved.is_active)
        self.assertEqual(retrieved.online_status, 'offline')
    
    def test_user_relationships(self):
        """Test user relationships"""
        # Create two users
        user1 = User(
            username='user1',
            email='user1@example.com',
            password_hash='hash1',
            public_key='key1',
            encrypted_private_key='encrypted1'
        )
        user2 = User(
            username='user2',
            email='user2@example.com',
            password_hash='hash2',
            public_key='key2',
            encrypted_private_key='encrypted2'
        )
        
        self.app.db.session.add_all([user1, user2])
        self.app.db.session.commit()
        
        # Create friend request
        friend_request = FriendRequest(
            sender_id=user1.id,
            receiver_id=user2.id,
            status='pending'
        )
        self.app.db.session.add(friend_request)
        self.app.db.session.commit()
        
        # Verify relationships
        self.assertEqual(len(user1.friend_requests_sent.all()), 1)
        self.assertEqual(len(user2.friend_requests_received.all()), 1)
        
        # Accept friend request
        friend_request.accept()
        
        # Verify friendship was created
        self.assertEqual(len(user1.friends_as_user.all()), 1)
        self.assertEqual(len(user2.friends_as_user.all()), 1)
        
        friendship = Friend.query.filter_by(user_id=user1.id, friend_id=user2.id).first()
        self.assertIsNotNone(friendship)
        self.assertFalse(friendship.is_blocked)
    
    def test_create_message(self):
        """Test message creation"""
        # Create users
        sender = User(
            username='sender',
            email='sender@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        recipient = User(
            username='recipient',
            email='recipient@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        self.app.db.session.add_all([sender, recipient])
        self.app.db.session.commit()
        
        # Create message
        message = Message(
            sender_id=sender.id,
            recipient_type='user',
            recipient_id=recipient.id,
            encrypted_message='encrypted_content',
            encrypted_aes_key='aes_key',
            nonce='nonce',
            tag='tag',
            digital_signature='signature',
            message_type='text'
        )
        self.app.db.session.add(message)
        self.app.db.session.commit()
        
        # Verify message
        retrieved = Message.query.first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.sender_id, sender.id)
        self.assertEqual(retrieved.recipient_id, recipient.id)
        self.assertEqual(retrieved.recipient_type, 'user')
        self.assertEqual(retrieved.message_type, 'text')
        self.assertFalse(retrieved.is_deleted)
        self.assertFalse(retrieved.is_edited)
        
        # Create message status
        status = MessageStatus(
            message_id=message.id,
            user_id=recipient.id,
            status='delivered'
        )
        self.app.db.session.add(status)
        self.app.db.session.commit()
        
        # Verify message status
        retrieved_status = MessageStatus.query.first()
        self.assertIsNotNone(retrieved_status)
        self.assertEqual(retrieved_status.status, 'delivered')
    
    def test_group_creation(self):
        """Test group creation and membership"""
        # Create users
        creator = User(
            username='creator',
            email='creator@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        member1 = User(
            username='member1',
            email='member1@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        member2 = User(
            username='member2',
            email='member2@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        self.app.db.session.add_all([creator, member1, member2])
        self.app.db.session.commit()
        
        # Create group
        group = Group(
            group_name='Test Group',
            group_description='A test group',
            created_by=creator.id,
            is_private=False
        )
        self.app.db.session.add(group)
        self.app.db.session.commit()
        
        # Add members
        group.add_member(creator.id, 'admin')
        group.add_member(member1.id, 'member')
        group.add_member(member2.id, 'member')
        
        # Verify group
        retrieved_group = Group.query.first()
        self.assertIsNotNone(retrieved_group)
        self.assertEqual(retrieved_group.group_name, 'Test Group')
        self.assertEqual(retrieved_group.get_member_count(), 3)
        
        # Verify memberships
        members = retrieved_group.get_active_members()
        self.assertEqual(len(members), 3)
        
        # Check admin status
        self.assertTrue(retrieved_group.is_admin(creator.id))
        self.assertFalse(retrieved_group.is_admin(member1.id))
        
        # Remove member
        retrieved_group.remove_member(member2.id)
        self.assertEqual(retrieved_group.get_member_count(), 2)
    
    def test_notification_creation(self):
        """Test notification creation"""
        # Create user
        user = User(
            username='notifyuser',
            email='notify@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        self.app.db.session.add(user)
        self.app.db.session.commit()
        
        # Create notification
        from models import Notification
        notification = Notification(
            user_id=user.id,
            notification_type='message',
            sender_id=1,
            message='Test notification',
            is_read=False
        )
        self.app.db.session.add(notification)
        self.app.db.session.commit()
        
        # Verify notification
        retrieved = Notification.query.first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.user_id, user.id)
        self.assertEqual(retrieved.notification_type, 'message')
        self.assertFalse(retrieved.is_read)
        
        # Mark as read
        retrieved.mark_as_read()
        self.assertTrue(retrieved.is_read)
        self.assertIsNotNone(retrieved.read_at)
    
    def test_audit_log_creation(self):
        """Test audit log creation"""
        # Create user
        user = User(
            username='audituser',
            email='audit@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        self.app.db.session.add(user)
        self.app.db.session.commit()
        
        # Create audit log
        from models import AuditLog
        audit_log = AuditLog(
            user_id=user.id,
            action='login',
            resource_type='user',
            resource_id=user.id,
            status='success',
            details={'ip': '127.0.0.1'}
        )
        self.app.db.session.add(audit_log)
        self.app.db.session.commit()
        
        # Verify audit log
        retrieved = AuditLog.query.first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.user_id, user.id)
        self.assertEqual(retrieved.action, 'login')
        self.assertEqual(retrieved.status, 'success')
        self.assertEqual(retrieved.details['ip'], '127.0.0.1')
    
    def test_user_methods(self):
        """Test user model methods"""
        # Create user
        user = User(
            username='methoduser',
            email='method@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        self.app.db.session.add(user)
        self.app.db.session.commit()
        
        # Test is_online property
        self.assertFalse(user.is_online)
        user.online_status = 'online'
        self.assertTrue(user.is_online)
        
        # Test update_online_status
        user.update_online_status('away')
        self.assertEqual(user.online_status, 'away')
        
        # Test update_last_seen
        old_last_seen = user.last_seen
        user.update_last_seen()
        self.assertNotEqual(user.last_seen, old_last_seen)
        
        # Test to_dict
        user_dict = user.to_dict()
        self.assertIn('id', user_dict)
        self.assertIn('username', user_dict)
        self.assertIn('email', user_dict)
        self.assertIn('online_status', user_dict)
    
    def test_message_methods(self):
        """Test message model methods"""
        # Create users
        sender = User(
            username='msgsender',
            email='sender@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        recipient = User(
            username='msgrecipient',
            email='recipient@example.com',
            password_hash='hash',
            public_key='key',
            encrypted_private_key='encrypted'
        )
        self.app.db.session.add_all([sender, recipient])
        self.app.db.session.commit()
        
        # Create message
        message = Message(
            sender_id=sender.id,
            recipient_type='user',
            recipient_id=recipient.id,
            encrypted_message='encrypted',
            encrypted_aes_key='aes',
            nonce='nonce',
            tag='tag',
            digital_signature='sig'
        )
        self.app.db.session.add(message)
        self.app.db.session.commit()
        
        # Create message status
        status = MessageStatus(
            message_id=message.id,
            user_id=recipient.id,
            status='sent'
        )
        self.app.db.session.add(status)
        self.app.db.session.commit()
        
        # Test mark_as_read
        message.mark_as_read(recipient.id)
        updated_status = MessageStatus.query.first()
        self.assertEqual(updated_status.status, 'read')
        self.assertIsNotNone(updated_status.read_at)
        
        # Test get_status_for_user
        retrieved_status = message.get_status_for_user(recipient.id)
        self.assertEqual(retrieved_status.status, 'read')
        
        # Test is_expired
        self.assertFalse(message.is_expired())
        message.expires_at = datetime.utcnow() - timedelta(minutes=5)
        self.assertTrue(message.is_expired())