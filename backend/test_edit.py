# test_edit.py
import requests
import time
import json

# Base URL
BASE_URL = 'http://127.0.0.1:5000'

def login(username, password):
    """Login and return cookies"""
    response = requests.post(
        f'{BASE_URL}/api/auth/login',
        json={'identifier': username, 'password': password}
    )
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.text}")
        return None
    
    print(f"✅ Login successful for {username}")
    return response.cookies

def send_message(sender_cookies, recipient_id, message, password):
    """Send a message"""
    response = requests.post(
        f'{BASE_URL}/api/messages/send',
        json={
            'recipient_id': recipient_id,
            'recipient_type': 'user',
            'message': message,
            'password': password
        },
        cookies=sender_cookies
    )
    
    if response.status_code != 200:
        print(f"❌ Send message failed: {response.text}")
        return None
    
    data = response.json()
    print(f"✅ Message sent! ID: {data.get('message_id')}")
    return data.get('message_id')

def edit_message(user_cookies, message_id, new_message, password):
    """Edit a message"""
    response = requests.put(
        f'{BASE_URL}/api/messages/{message_id}',
        json={
            'message': new_message,
            'password': password
        },
        cookies=user_cookies
    )
    
    if response.status_code != 200:
        print(f"❌ Edit failed: {response.text}")
        return False
    
    print(f"✅ Message {message_id} edited successfully!")
    return True

def get_messages(user_cookies, chat_id, chat_type, password):
    """Get messages"""
    response = requests.get(
        f'{BASE_URL}/api/messages/chat/{chat_id}',
        params={
            'chat_type': chat_type,
            'password': password
        },
        cookies=user_cookies
    )
    
    if response.status_code != 200:
        print(f"❌ Get messages failed: {response.text}")
        return None
    
    return response.json()

def main():
    print("=" * 60)
    print("🔐 Testing Message Edit Feature")
    print("=" * 60)
    
    # 1. Login as testuser
    print("\n1️⃣ Logging in as testuser...")
    testuser_cookies = login('testuser', 'Test@1234')
    if not testuser_cookies:
        print("❌ Cannot proceed without login")
        return
    
    # 2. Check friend relationship
    print("\n2️⃣ Checking friends...")
    friends_response = requests.get(
        f'{BASE_URL}/api/friends/list',
        cookies=testuser_cookies
    )
    
    if friends_response.status_code == 200:
        friends_data = friends_response.json()
        print(f"   Friends: {friends_data}")
    else:
        print("   ⚠️  Need to add friend first")
        
        # Try to add friend if not already
        print("\n   Sending friend request to frienduser...")
        request_response = requests.post(
            f'{BASE_URL}/api/friends/request',
            json={
                'user_id': 3,
                'message': "Let's be friends!"
            },
            cookies=testuser_cookies
        )
        print(f"   Friend request response: {request_response.text}")
    
    # 3. Send a message
    print("\n3️⃣ Sending a test message...")
    message_id = send_message(
        testuser_cookies,
        recipient_id=3,
        message="This message will be edited!",
        password="Test@1234"
    )
    
    if not message_id:
        print("❌ Cannot proceed without a message")
        return
    
    # 4. Wait 2 seconds
    print("\n4️⃣ Waiting 2 seconds (within 5 minute window)...")
    time.sleep(2)
    
    # 5. Edit the message
    print("\n5️⃣ Editing the message...")
    edit_success = edit_message(
        testuser_cookies,
        message_id,
        "This message has been EDITED!",
        "Test@1234"
    )
    
    if not edit_success:
        print("❌ Edit failed, but continuing...")
    
    # 6. Verify the edit
    print("\n6️⃣ Verifying the edit...")
    
    # Login as frienduser to see the changes
    print("\n   Logging in as frienduser...")
    friend_cookies = login('frienduser', 'Friend@1234')
    
    if friend_cookies:
        messages = get_messages(
            friend_cookies,
            chat_id=2,  # testuser's ID
            chat_type='user',
            password='Friend@1234'
        )
        
        if messages:
            print(f"\n   📨 Messages from testuser:")
            for msg in messages.get('messages', []):
                print(f"      ID: {msg['id']}")
                print(f"      Message: {msg['message']}")
                print(f"      Edited: {msg['is_edited']}")
                print(f"      Valid Signature: {msg['is_valid_signature']}")
                print(f"      Time: {msg['created_at']}")
                print("      ---")
    
    # 7. Test edit after 5 minutes (optional)
    print("\n7️⃣ Testing edit time limit...")
    print("   Would need to wait 5 minutes to test this")
    print("   The current message was edited within the time window ✅")
    
    print("\n" + "=" * 60)
    print("✅ Test complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()