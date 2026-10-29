# backend/tests/test_messages.py
import pytest
import json
from models import Message, MessageStatus, User
from services.message_service import MessageService
from services.friend_service import FriendService
from . import BaseTestCase

class TestMessages(BaseTestCase):
    """Test message-related endpoints and services"""
    
    def setUp(self):
        """Set up test with two users who are friends"""
        super().setUp()
        
        # Create two users
        self.user1, self.token1 = self.create_test_user(
            username='user1',
            email='user1@example.com',
            password='Test@123'
        )
        
        self.user2, self.token2 = self.create_test_user(
            username='user2',
            email='user2@example.com',
            password='Test@123'
        )
        
        # Make them friends
        FriendService.send_friend_request(self.user1.id, self.user2.id)
        FriendService.accept_friend_request(
            FriendService.get_friend_requests(self.user2.id)['received'][0]['id'],
            self.user2.id
        )
    
    def test_send_message_success(self):
        """Test sending a message successfully"""
        response = self.client.post('/api/messages/send',
            headers=self.get_auth_headers(self.token1),
            json={
                'recipient_id': self.user2.id,
                'recipient_type': 'user',
                'message': 'Hello, this is a test message!',
                'password': 'Test@123'
            })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Message sent successfully')
        self.assertIn('message_id', data)
        
        # Verify message was created
        message = Message.query.get(data['message_id'])
        self.assertIsNotNone(message)
        self.assertEqual(message.sender_id, self.user1.id)
        self.assertEqual(message.recipient_id, self.user2.id)
        self.assertEqual(message.recipient_type, 'user')
        
        # Verify message status
        status = MessageStatus.query.filter_by(
            message_id=message.id,
            user_id=self.user2.id
        ).first()
        self.assertIsNotNone(status)
        self.assertEqual(status.status, 'delivered')
    
    def test_send_message_not_friends(self):
        """Test sending message to non-friend"""
        # Create third user (not friends)
        user3, token3 = self.create_test_user(
            username='user3',
            email='user3@example.com',
            password='Test@123'
        )
        
        response = self.client.post('/api/messages/send',
            headers=self.get_auth_headers(self.token1),
            json={
                'recipient_id': user3.id,
                'recipient_type': 'user',
                'message': 'Hello, stranger!',
                'password': 'Test@123'
            })
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'You can only send messages to friends')
    
    def test_get_messages(self):
        """Test getting messages between users"""
        # Send some messages
        for i in range(3):
            self.client.post('/api/messages/send',
                headers=self.get_auth_headers(self.token1),
                json={
                    'recipient_id': self.user2.id,
                    'recipient_type': 'user',
                    'message': f'Message {i+1}',
                    'password': 'Test@123'
                })
        
        # Get messages
        response = self.client.get(f'/api/messages/chat/{self.user2.id}?chat_type=user&password=Test@123',
            headers=self.get_auth_headers(self.token1))
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('messages', data)
        self.assertEqual(len(data['messages']), 3)
        self.assertIn('chat_info', data)
    
    def test_edit_message(self):
        """Test editing a message"""
        # Send a message
        send_response = self.client.post('/api/messages/send',
            headers=self.get_auth_headers(self.token1),
            json={
                'recipient_id': self.user2.id,
                'recipient_type': 'user',
                'message': 'Original message',
                'password': 'Test@123'
            })
        
        send_data = json.loads(send_response.data)
        message_id = send_data['message_id']
        
        # Edit the message
        response = self.client.put(f'/api/messages/{message_id}',
            headers=self.get_auth_headers(self.token1),
            json={
                'message': 'Edited message',
                'password': 'Test@123'
            })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Message edited successfully')
        
        # Verify message was edited
        message = Message.query.get(message_id)
        self.assertTrue(message.is_edited)
        self.assertIsNotNone(message.edited_at)
    
    def test_delete_message(self):
        """Test deleting a message"""
        # Send a message
        send_response = self.client.post('/api/messages/send',
            headers=self.get_auth_headers(self.token1),
            json={
                'recipient_id': self.user2.id,
                'recipient_type': 'user',
                'message': 'Message to delete',
                'password': 'Test@123'
            })
        
        send_data = json.loads(send_response.data)
        message_id = send_data['message_id']
        
        # Delete the message
        response = self.client.delete(f'/api/messages/{message_id}',
            headers=self.get_auth_headers(self.token1),
            json={'delete_for_everyone': True})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Message deleted successfully')
        
        # Verify message is soft deleted
        message = Message.query.get(message_id)
        self.assertTrue(message.is_deleted)
    
    def test_add_reaction(self):
        """Test adding reaction to a message"""
        # Send a message
        send_response = self.client.post('/api/messages/send',
            headers=self.get_auth_headers(self.token1),
            json={
                'recipient_id': self.user2.id,
                'recipient_type': 'user',
                'message': 'Message with reaction',
                'password': 'Test@123'
            })
        
        send_data = json.loads(send_response.data)
        message_id = send_data['message_id']
        
        # Add reaction
        response = self.client.post(f'/api/messages/{message_id}/reaction',
            headers=self.get_auth_headers(self.token2),
            json={'reaction': '👍'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Reaction added successfully')
        
        # Verify reaction
        message = Message.query.get(message_id)
        reactions = message.get_reaction_summary()
        self.assertEqual(reactions['👍'], 1)
    
    def test_unread_count(self):
        """Test getting unread message count"""
        # Send messages from user1 to user2
        for i in range(3):
            self.client.post('/api/messages/send',
                headers=self.get_auth_headers(self.token1),
                json={
                    'recipient_id': self.user2.id,
                    'recipient_type': 'user',
                    'message': f'Unread message {i+1}',
                    'password': 'Test@123'
                })
        
        # Get unread count for user2
        response = self.client.get('/api/messages/unread',
            headers=self.get_auth_headers(self.token2))
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['unread_count'], 3)
        self.assertEqual(data['direct'], 3)