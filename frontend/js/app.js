// ============================================
// MAIN APPLICATION
// ============================================

class SecureChatApp {
    constructor() {
        this.currentUser = null;
        this.currentChat = null;
        this.currentView = 'chat';
        this.socket = null;
        this.isConnected = false;
        this.isInitialized = false;
        this.init();
    }

    init() {
        console.log('🚀 Initializing Secure Chat App...');
        
        // Setup event listeners
        this.setupAuthEvents();
        this.setupNavigationEvents();
        this.setupChatEvents();
        this.setupFriendEvents();
        this.setupGroupEvents();
        this.setupProfileEvents();
        this.setupNotificationEvents();
        this.setupSettingsEvents();
        this.setupModalEvents();
        this.setupEmojiPicker();
        this.setupViewEvents();

        // Check if user is logged in
        const token = localStorage.getItem('access_token') || this.getCookie('access_token');
        if (token) {
            console.log('🔑 Token found, loading user...');
            this.loadUser();
        } else {
            console.log('🔑 No token found, showing login page');
            this.showLoginPage();
        }

        this.isInitialized = true;
        console.log('✅ App initialized');
    }

    // ==========================================
    // UTILITY
    // ==========================================
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    // ==========================================
    // PAGE MANAGEMENT
    // ==========================================
    showLoginPage() {
        document.getElementById('auth-page').classList.add('active');
        document.getElementById('main-app').classList.remove('active');
        document.querySelectorAll('.auth-form-page').forEach(p => p.classList.remove('active'));
        document.getElementById('login-page').classList.add('active');
    }

    showMainApp() {
        console.log('📱 Showing main app...');
        document.getElementById('auth-page').classList.remove('active');
        document.getElementById('main-app').classList.add('active');
        document.getElementById('sidebar').classList.remove('open');
    }

    showPage(pageId) {
        document.querySelectorAll('.auth-form-page').forEach(p => p.classList.remove('active'));
        document.getElementById(pageId).classList.add('active');
    }

    // ==========================================
    // AUTH
    // ==========================================
    setupAuthEvents() {
        // Login
        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const identifier = document.getElementById('login-identifier').value;
            const password = document.getElementById('login-password').value;
            await this.login(identifier, password);
        });

        // Show register
        document.getElementById('show-register').addEventListener('click', (e) => {
            e.preventDefault();
            this.showPage('register-page');
        });

        // Show login
        document.getElementById('show-login').addEventListener('click', (e) => {
            e.preventDefault();
            this.showPage('login-page');
        });

        // Register
        document.getElementById('register-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('register-username').value;
            const email = document.getElementById('register-email').value;
            const fullName = document.getElementById('register-fullname').value;
            const password = document.getElementById('register-password').value;
            const confirm = document.getElementById('register-confirm').value;

            if (password !== confirm) {
                Utils.showError('Passwords do not match');
                return;
            }

            await this.register(username, email, password, fullName);
        });

        // Password strength
        document.getElementById('register-password').addEventListener('input', (e) => {
            this.updatePasswordStrength(e.target.value);
        });

        // Forgot password
        document.getElementById('forgot-password-link').addEventListener('click', (e) => {
            e.preventDefault();
            Utils.showToast('Password reset feature coming soon!', 'info');
        });

        // Logout
        document.getElementById('logout-btn').addEventListener('click', () => {
            if (confirm('Are you sure you want to logout?')) {
                this.logout();
            }
        });
    }

    async login(identifier, password) {
        console.log('🔐 Attempting login...', { identifier });
        const errorEl = document.getElementById('login-error');
        errorEl.classList.remove('show');
        errorEl.textContent = '';

        try {
            const result = await AuthAPI.login({ identifier, password });
            console.log('✅ Login response:', result);
            
            // Try to get token from cookies first
            let accessToken = this.getCookie('access_token');
            let refreshToken = this.getCookie('refresh_token');
            
            // If not in cookies, try from response body
            if (!accessToken && result.access_token) {
                accessToken = result.access_token;
            }
            if (!refreshToken && result.refresh_token) {
                refreshToken = result.refresh_token;
            }
            
            if (accessToken) {
                // Store tokens
                API.setToken(accessToken);
                if (refreshToken) {
                    localStorage.setItem('refresh_token', refreshToken);
                }
                
                // Store user
                this.currentUser = result.user;
                localStorage.setItem('user', JSON.stringify(this.currentUser));
                
                // Show main app
                this.showMainApp();
                this.loadUserData();
                
                Utils.showToast('Login successful!', 'success');
                console.log('👤 User logged in:', this.currentUser.username);
            } else {
                Utils.showError('Login failed: No token received');
                console.error('❌ No token in response or cookies:', result);
                console.log('📝 Cookies:', document.cookie);
            }
        } catch (error) {
            console.error('❌ Login error:', error);
            errorEl.textContent = error.message || 'Login failed. Please check your credentials.';
            errorEl.classList.add('show');
        }
    }

    async register(username, email, password, fullName) {
        console.log('📝 Attempting registration...', { username, email });
        const errorEl = document.getElementById('register-error');
        errorEl.classList.remove('show');
        errorEl.textContent = '';

        try {
            const result = await AuthAPI.register({ 
                username, 
                email, 
                password, 
                full_name: fullName 
            });
            console.log('✅ Registration response:', result);
            
            Utils.showToast('Registration successful! Please login.', 'success');
            this.showPage('login-page');
            document.getElementById('login-identifier').value = username;
            document.getElementById('login-password').value = '';
        } catch (error) {
            console.error('❌ Registration error:', error);
            errorEl.textContent = error.message || 'Registration failed. Please try again.';
            errorEl.classList.add('show');
        }
    }

    async logout() {
        console.log('🚪 Logging out...');
        try {
            await AuthAPI.logout();
        } catch (e) {
            console.warn('Logout API error:', e);
        }
        
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        API.setToken(null);
        this.currentUser = null;
        this.disconnectSocket();
        
        this.showLoginPage();
        
        Utils.showToast('Logged out successfully', 'info');
        console.log('✅ Logged out');
    }

    async loadUser() {
        try {
            console.log('🔄 Loading user profile...');
            const result = await AuthAPI.getProfile();
            this.currentUser = result.user || result.profile;
            console.log('👤 User loaded:', this.currentUser.username);
            
            localStorage.setItem('user', JSON.stringify(this.currentUser));
            
            this.showMainApp();
            this.loadUserData();
        } catch (error) {
            console.error('❌ Failed to load user:', error);
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user');
            API.setToken(null);
            this.currentUser = null;
            this.showLoginPage();
        }
    }

    loadUserData() {
        if (!this.currentUser) return;
        
        console.log('📊 Loading user data for:', this.currentUser.username);
        
        document.getElementById('sidebar-username').textContent = this.currentUser.username;
        document.getElementById('sidebar-status-text').textContent = this.currentUser.online_status || 'Offline';
        this.updateStatusIndicator(this.currentUser.online_status);
        
        if (this.currentUser.profile_picture) {
            document.querySelector('.sidebar-avatar img').src = this.currentUser.profile_picture;
        }
        
        this.connectSocket();
        this.loadChats();
        this.loadNotifications();
    }

    updatePasswordStrength(password) {
        const container = document.getElementById('password-strength');
        if (!container) return;
        
        let strength = 0;
        if (password.length >= 8) strength++;
        if (/[a-z]/.test(password)) strength++;
        if (/[A-Z]/.test(password)) strength++;
        if (/\d/.test(password)) strength++;
        if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength++;

        const labels = ['Very Weak', 'Weak', 'Fair', 'Good', 'Strong', 'Very Strong'];
        const colors = ['#f44336', '#f44336', '#ff9800', '#ffeb3b', '#4caf50', '#2e7d32'];
        const width = (strength / 5) * 100;

        container.innerHTML = `
            <div style="margin-top:4px;">
                <div style="height:4px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                    <div style="height:100%;width:${width}%;background:${colors[strength]};border-radius:4px;transition:width 0.3s;"></div>
                </div>
                <span style="font-size:12px;color:${colors[strength]};">${labels[strength]}</span>
            </div>
        `;
    }

    updateStatusIndicator(status, targetId = 'sidebar-status') {
        const el = document.getElementById(targetId);
        if (!el) return;
        el.className = 'status-indicator';
        if (status) el.classList.add(status);
    }

    // ==========================================
    // SOCKET
    // ==========================================
    connectSocket() {
        const socketUrl = localStorage.getItem('socket_url') || 'ws://127.0.0.1:5000';
        console.log('🔌 Connecting to WebSocket:', socketUrl);
        
        try {
            this.socket = new WebSocket(`${socketUrl}?token=${API.token}`);

            this.socket.onopen = () => {
                console.log('✅ WebSocket connected');
                this.isConnected = true;
            };

            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleSocketMessage(data);
                } catch (e) {
                    console.error('❌ Failed to parse WebSocket message:', e);
                }
            };

            this.socket.onclose = () => {
                console.log('🔌 WebSocket disconnected');
                this.isConnected = false;
                setTimeout(() => this.connectSocket(), 5000);
            };

            this.socket.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
                this.isConnected = false;
            };
        } catch (error) {
            console.error('❌ Failed to create WebSocket:', error);
        }
    }

    disconnectSocket() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
            this.isConnected = false;
        }
    }

    handleSocketMessage(data) {
        console.log('📨 WebSocket message:', data);
        switch (data.type) {
            case 'new_message':
                this.handleNewMessage(data);
                break;
            case 'typing_indicator':
                this.handleTypingIndicator(data);
                break;
            case 'user_online':
                this.handleUserStatus(data);
                break;
            case 'user_offline':
                this.handleUserStatus(data);
                break;
            case 'friend_request':
                this.handleFriendRequest(data);
                break;
            case 'notification':
                this.handleNotification(data);
                break;
        }
    }

    // ==========================================
    // NAVIGATION
    // ==========================================
    setupNavigationEvents() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.dataset.view;
                this.switchView(view);
            });
        });

        document.getElementById('sidebar-close').addEventListener('click', () => {
            document.getElementById('sidebar').classList.remove('open');
        });
    }

    switchView(view) {
        this.currentView = view;
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(`view-${view}`).classList.add('active');
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelector(`.nav-item[data-view="${view}"]`).classList.add('active');

        switch(view) {
            case 'chat': this.loadChats(); break;
            case 'friends': this.loadFriends(); break;
            case 'groups': this.loadGroups(); break;
            case 'notifications': this.loadNotifications(); break;
            case 'profile': this.loadProfile(); break;
            case 'settings': this.renderSettings(); break;
        }
    }

    setupViewEvents() {
        document.getElementById('chat-back-btn').addEventListener('click', () => {
            document.querySelector('.chat-list-panel').style.display = 'block';
            document.querySelector('.chat-window-panel').style.display = 'none';
        });

        document.getElementById('new-chat-btn').addEventListener('click', () => {
            this.openModal('New Chat', this.getNewChatModalContent());
        });
    }

    // ==========================================
    // CHAT EVENTS
    // ==========================================
    setupChatEvents() {
        document.getElementById('send-btn').addEventListener('click', () => {
            this.sendMessage();
        });

        document.getElementById('message-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        let typingTimeout;
        document.getElementById('message-input').addEventListener('input', () => {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({
                    type: 'typing',
                    chat_id: this.currentChat,
                    is_typing: true
                }));
                clearTimeout(typingTimeout);
                typingTimeout = setTimeout(() => {
                    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                        this.socket.send(JSON.stringify({
                            type: 'typing',
                            chat_id: this.currentChat,
                            is_typing: false
                        }));
                    }
                }, 2000);
            }
        });

        document.getElementById('chat-search').addEventListener('input', Utils.debounce((e) => {
            this.filterChats(e.target.value);
        }, 300));

        document.getElementById('emoji-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            const picker = document.getElementById('emoji-picker');
            picker.style.display = picker.style.display === 'block' ? 'none' : 'block';
        });

        document.getElementById('attach-btn').addEventListener('click', () => {
            this.openFileUpload();
        });

        document.getElementById('mic-btn').addEventListener('click', () => {
            this.startVoiceRecording();
        });

        document.getElementById('chat-menu-btn').addEventListener('click', () => {
            this.showChatMenu();
        });

        document.getElementById('chat-search-btn').addEventListener('click', () => {
            this.openModal('Search Messages', this.getChatSearchModal());
        });
    }

    // ==========================================
    // FRIEND EVENTS
    // ==========================================
    setupFriendEvents() {
        document.getElementById('add-friend-btn').addEventListener('click', () => {
            this.openModal('Add Friend', this.getAddFriendModal());
        });

        document.querySelectorAll('#friends-content .tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#friends-content .tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const tab = btn.dataset.tab;
                if (tab === 'friends') this.renderFriends();
                else if (tab === 'requests') this.renderFriendRequests();
                else if (tab === 'search') this.renderFriendSearch();
            });
        });
    }

    // ==========================================
    // GROUP EVENTS
    // ==========================================
    setupGroupEvents() {
        document.getElementById('create-group-btn').addEventListener('click', () => {
            this.openModal('Create Group', this.getCreateGroupModal());
        });
    }

    // ==========================================
    // PROFILE EVENTS
    // ==========================================
    setupProfileEvents() {
        // Profile events handled in render
    }

    // ==========================================
    // NOTIFICATION EVENTS
    // ==========================================
    setupNotificationEvents() {
        document.getElementById('mark-all-read-btn').addEventListener('click', async () => {
            try {
                await NotificationsAPI.markAllAsRead();
                this.loadNotifications();
                Utils.showToast('All notifications marked as read', 'success');
            } catch (error) {
                Utils.showError('Failed to mark all as read: ' + error.message);
            }
        });
    }

    // ==========================================
    // SETTINGS EVENTS
    // ==========================================
    setupSettingsEvents() {
        // Settings events handled in render
    }

    // ==========================================
    // MODAL EVENTS
    // ==========================================
    setupModalEvents() {
        document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeModal();
        });
    }

    // ==========================================
    // EMOJI PICKER
    // ==========================================
    setupEmojiPicker() {
        const emojis = ['😊', '😂', '❤️', '👍', '🎉', '🔥', '💯', '🤔', '🙏', '✨', '😍', '🥰', '😘', '😎', '🤩', '🥳', '😏', '😒', '😞', '😔', '😟', '😕', '🙁', '☹️', '😣', '😖', '😫', '😩', '🥺', '😢', '😭', '😤', '😠', '😡', '🤬', '🤯', '😳', '🥵', '🥶', '😱', '😨', '😰', '😥', '😓', '🤗', '🤔', '🤭', '🤫', '🤥', '😶', '😐', '😑', '😬', '🙄', '😯', '😦', '😧', '😮', '😲', '😴', '🤤', '😪', '😵', '🤐', '🥴', '🤢', '🤮', '🤧', '😷', '🤒', '🤕', '🤑', '🤠'];

        const container = document.getElementById('emoji-picker');
        container.innerHTML = `
            <div class="emoji-grid">
                ${emojis.map(e => `<button onclick="app.insertEmoji('${e}')">${e}</button>`).join('')}
            </div>
        `;

        document.addEventListener('click', (e) => {
            if (!e.target.closest('#emoji-picker') && !e.target.closest('#emoji-btn')) {
                container.style.display = 'none';
            }
        });
    }

    // ==========================================
    // CHAT METHODS
    // ==========================================
    async loadChats() {
        try {
            const result = await UsersAPI.getContacts();
            const chats = result.friends || [];
            this.renderChatList(chats);
        } catch (error) {
            console.error('Error loading chats:', error);
        }
    }

    renderChatList(chats) {
        const container = document.getElementById('chat-list');
        if (!chats || chats.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted" style="padding:40px 16px;">
                    <p>No conversations yet</p>
                    <p style="font-size:13px;">Start chatting with your friends!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = chats.map(chat => `
            <div class="chat-list-item" data-chat-id="${chat.id}" onclick="app.openChat(${chat.id})">
                <img class="chat-avatar" src="${chat.profile_picture || 'assets/images/default-avatar.png'}" alt="${chat.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                <div class="chat-info">
                    <div class="chat-name">${Utils.escapeHTML(chat.full_name || chat.username)}</div>
                    <div class="chat-last-msg">${chat.last_message ? Utils.escapeHTML(chat.last_message) : 'No messages'}</div>
                </div>
                <div class="chat-meta">
                    <div class="chat-time">${chat.last_message_time ? Utils.formatDate(chat.last_message_time) : ''}</div>
                    ${chat.unread_count ? `<div class="chat-unread">${chat.unread_count}</div>` : ''}
                </div>
            </div>
        `).join('');

        const totalUnread = chats.reduce((sum, c) => sum + (c.unread_count || 0), 0);
        document.getElementById('chat-badge').textContent = totalUnread || '0';
    }

    filterChats(query) {
        const items = document.querySelectorAll('.chat-list-item');
        items.forEach(item => {
            const name = item.querySelector('.chat-name').textContent.toLowerCase();
            const match = name.includes(query.toLowerCase());
            item.style.display = match ? 'flex' : 'none';
        });
    }

    openChat(chatId) {
        this.currentChat = chatId;
        document.querySelector('.chat-list-panel').style.display = 'none';
        document.querySelector('.chat-window-panel').style.display = 'flex';
        this.loadChatMessages(chatId);
        this.getChatUserInfo(chatId);
        document.querySelectorAll('.chat-list-item').forEach(el => el.classList.remove('active'));
        document.querySelector(`.chat-list-item[data-chat-id="${chatId}"]`)?.classList.add('active');
    }

    async loadChatMessages(chatId) {
        const password = prompt('Enter your password to decrypt messages:');
        if (!password) return;

        try {
            const result = await MessagesAPI.getMessages(chatId, {
                chat_type: 'user',
                limit: 50,
                password: password
            });
            this.renderMessages(result.messages || []);
        } catch (error) {
            Utils.showError('Failed to load messages: ' + error.message);
        }
    }

    renderMessages(messages) {
        const container = document.getElementById('chat-messages');
        if (!messages || messages.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted" style="padding:40px;">
                    <p>No messages yet</p>
                    <p style="font-size:13px;">Send a message to start the conversation!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = messages.map(msg => `
            <div class="message ${msg.sender_id === this.currentUser?.id ? 'sent' : 'received'}">
                <div class="msg-text">${Utils.escapeHTML(msg.message)}</div>
                <div class="msg-meta">
                    <span class="msg-time">${Utils.formatTime(msg.created_at)}</span>
                    ${msg.is_edited ? '<span class="msg-edited">edited</span>' : ''}
                    ${msg.is_valid_signature ? '✓' : '⚠️'}
                </div>
            </div>
        `).join('');

        container.scrollTop = container.scrollHeight;
    }

    async getChatUserInfo(chatId) {
        try {
            const result = await UsersAPI.getUser(chatId);
            const user = result.user;
            document.getElementById('chat-name').textContent = user.full_name || user.username;
            document.getElementById('chat-avatar').src = user.profile_picture || 'assets/images/default-avatar.png';
            document.getElementById('chat-status').textContent = user.online_status || 'Offline';
        } catch (error) {
            console.error('Error loading chat user:', error);
        }
    }

    async sendMessage() {
        const input = document.getElementById('message-input');
        const message = input.value.trim();
        if (!message || !this.currentChat) return;

        const password = prompt('Enter your password to encrypt the message:');
        if (!password) return;

        try {
            const result = await MessagesAPI.send({
                recipient_id: this.currentChat,
                recipient_type: 'user',
                message: message,
                password: password
            });
            input.value = '';
            this.loadChatMessages(this.currentChat);
        } catch (error) {
            Utils.showError('Failed to send message: ' + error.message);
        }
    }

    // ==========================================
    // FRIENDS METHODS
    // ==========================================
    async loadFriends() {
        await this.renderFriends();
    }

    async renderFriends() {
        try {
            const result = await FriendsAPI.getFriends();
            const friends = result.friends || [];
            const container = document.getElementById('friends-content');
            
            if (!friends || friends.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-muted" style="padding:40px;">
                        <p>No friends yet</p>
                        <p style="font-size:13px;">Add friends to start chatting!</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = friends.map(f => `
                <div class="friend-card">
                    <img src="${f.profile_picture || 'assets/images/default-avatar.png'}" alt="${f.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                    <div class="friend-info">
                        <div class="friend-name">${Utils.escapeHTML(f.full_name || f.username)}</div>
                        <div class="friend-username">@${Utils.escapeHTML(f.username)}</div>
                    </div>
                    <div class="friend-actions">
                        <button class="btn-secondary" onclick="app.openChat(${f.id})">💬</button>
                        <button class="btn-danger" onclick="app.removeFriend(${f.id})">✕</button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            Utils.showError('Failed to load friends: ' + error.message);
        }
    }

    async renderFriendRequests() {
        try {
            const result = await FriendsAPI.getRequests();
            const requests = result.received || [];
            const container = document.getElementById('friends-content');
            
            if (!requests || requests.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-muted" style="padding:40px;">
                        <p>No pending friend requests</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = requests.map(r => `
                <div class="friend-request-card" data-request-id="${r.id}">
                    <div class="request-info">
                        <img src="${r.sender?.profile_picture || 'assets/images/default-avatar.png'}" alt="${r.sender?.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                        <div>
                            <div>${Utils.escapeHTML(r.sender?.full_name || r.sender?.username)}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">@${Utils.escapeHTML(r.sender?.username)}</div>
                            ${r.message ? `<div style="font-size:13px;color:var(--text-secondary);">"${Utils.escapeHTML(r.message)}"</div>` : ''}
                        </div>
                    </div>
                    <div class="request-actions">
                        <button class="btn-primary" onclick="app.acceptFriendRequest(${r.id})">Accept</button>
                        <button class="btn-danger" onclick="app.rejectFriendRequest(${r.id})">Reject</button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            Utils.showError('Failed to load friend requests: ' + error.message);
        }
    }

    renderFriendSearch() {
        const container = document.getElementById('friends-content');
        container.innerHTML = `
            <div class="search-bar" style="margin-bottom:16px;">
                <input type="text" id="friend-search-input" placeholder="Search for users..." />
                <span class="search-icon">🔍</span>
            </div>
            <div id="friend-search-results"></div>
        `;

        document.getElementById('friend-search-input').addEventListener('input', Utils.debounce(async (e) => {
            const query = e.target.value.trim();
            if (query.length < 2) {
                document.getElementById('friend-search-results').innerHTML = '';
                return;
            }
            try {
                const result = await FriendsAPI.searchUsers(query);
                const users = result.users || [];
                const resultsContainer = document.getElementById('friend-search-results');
                if (!users || users.length === 0) {
                    resultsContainer.innerHTML = `<div class="text-center text-muted" style="padding:20px;">No users found</div>`;
                    return;
                }
                resultsContainer.innerHTML = users.map(u => `
                    <div class="friend-card">
                        <img src="${u.profile_picture || 'assets/images/default-avatar.png'}" alt="${u.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                        <div class="friend-info">
                            <div class="friend-name">${Utils.escapeHTML(u.full_name || u.username)}</div>
                            <div class="friend-username">@${Utils.escapeHTML(u.username)}</div>
                        </div>
                        <div class="friend-actions">
                            ${u.is_friend ? '<span style="color:var(--success);">✓ Friend</span>' :
                              u.has_pending_request ? '<span style="color:var(--warning);">Pending</span>' :
                              `<button class="btn-primary" onclick="app.sendFriendRequest(${u.id})">Add</button>`}
                        </div>
                    </div>
                `).join('');
            } catch (error) {
                Utils.showError('Search failed: ' + error.message);
            }
        }, 300));
    }

    async sendFriendRequest(userId) {
        try {
            await FriendsAPI.sendRequest({ user_id: userId, message: 'Let\'s connect on Secure Chat!' });
            Utils.showToast('Friend request sent!', 'success');
            this.renderFriendSearch();
        } catch (error) {
            Utils.showError('Failed to send request: ' + error.message);
        }
    }

    async acceptFriendRequest(requestId) {
        try {
            await FriendsAPI.acceptRequest(requestId);
            Utils.showToast('Friend request accepted!', 'success');
            this.loadFriends();
        } catch (error) {
            Utils.showError('Failed to accept request: ' + error.message);
        }
    }

    async rejectFriendRequest(requestId) {
        try {
            await FriendsAPI.rejectRequest(requestId);
            Utils.showToast('Friend request rejected', 'info');
            this.loadFriends();
        } catch (error) {
            Utils.showError('Failed to reject request: ' + error.message);
        }
    }

    async removeFriend(friendId) {
        if (!confirm('Remove this friend?')) return;
        try {
            await FriendsAPI.removeFriend(friendId);
            Utils.showToast('Friend removed', 'info');
            this.loadFriends();
        } catch (error) {
            Utils.showError('Failed to remove friend: ' + error.message);
        }
    }

    // ==========================================
    // GROUPS METHODS
    // ==========================================
    async loadGroups() {
        try {
            const result = await GroupsAPI.getMyGroups();
            const groups = result.groups || [];
            const container = document.getElementById('groups-list');
            
            if (!groups || groups.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-muted" style="padding:40px;">
                        <p>No groups yet</p>
                        <p style="font-size:13px;">Create a group to chat with multiple friends!</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = groups.map(g => `
                <div class="group-card" onclick="app.openGroupChat(${g.id})">
                    <img src="${g.group_picture || 'assets/images/default-avatar.png'}" alt="${g.group_name}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                    <div class="group-info">
                        <div class="group-name">${Utils.escapeHTML(g.group_name)}</div>
                        <div class="group-members">👥 ${g.member_count || 0} members</div>
                        ${g.group_description ? `<div style="font-size:13px;color:var(--text-secondary);">${Utils.escapeHTML(g.group_description)}</div>` : ''}
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn-secondary" onclick="event.stopPropagation();app.openGroupSettings(${g.id})">⚙️</button>
                        <button class="btn-danger" onclick="event.stopPropagation();app.deleteGroup(${g.id})">✕</button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            Utils.showError('Failed to load groups: ' + error.message);
        }
    }

    async deleteGroup(groupId) {
        if (!confirm('Delete this group?')) return;
        try {
            await GroupsAPI.deleteGroup(groupId);
            Utils.showToast('Group deleted', 'info');
            this.loadGroups();
        } catch (error) {
            Utils.showError('Failed to delete group: ' + error.message);
        }
    }

    openGroupChat(groupId) {
        this.currentChat = groupId;
        document.querySelector('.chat-list-panel').style.display = 'none';
        document.querySelector('.chat-window-panel').style.display = 'flex';
        this.loadGroupMessages(groupId);
    }

    async loadGroupMessages(groupId) {
        const password = prompt('Enter your password to decrypt messages:');
        if (!password) return;

        try {
            const result = await MessagesAPI.getMessages(groupId, {
                chat_type: 'group',
                limit: 50,
                password: password
            });
            document.getElementById('chat-name').textContent = 'Group Chat';
            document.getElementById('chat-avatar').src = 'assets/images/default-avatar.png';
            document.getElementById('chat-status').textContent = 'Group';
            this.renderMessages(result.messages || []);
        } catch (error) {
            Utils.showError('Failed to load messages: ' + error.message);
        }
    }

    // ==========================================
    // NOTIFICATIONS METHODS
    // ==========================================
    async loadNotifications() {
        try {
            const result = await NotificationsAPI.getNotifications();
            const notifications = result.notifications || [];
            const unread = result.unread || 0;
            
            document.getElementById('notification-badge').textContent = unread || '0';

            const container = document.getElementById('notifications-list');
            if (!notifications || notifications.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-muted" style="padding:40px;">
                        <p>No notifications</p>
                        <p style="font-size:13px;">You're all caught up!</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = notifications.map(n => `
                <div class="notification-item ${n.is_read ? '' : 'unread'}" data-notif-id="${n.id}">
                    <div class="notif-icon">${this.getNotificationIcon(n.notification_type)}</div>
                    <div class="notif-content">
                        <div class="notif-message">${Utils.escapeHTML(n.message)}</div>
                        <div class="notif-time">${Utils.formatDate(n.created_at)}</div>
                    </div>
                    ${!n.is_read ? `<button class="btn-secondary" onclick="app.markNotificationRead(${n.id})">✓</button>` : ''}
                    <button class="btn-danger" onclick="app.deleteNotification(${n.id})">✕</button>
                </div>
            `).join('');
        } catch (error) {
            console.error('Error loading notifications:', error);
        }
    }

    getNotificationIcon(type) {
        const icons = {
            'message': '💬',
            'friend_request': '👤',
            'group_invite': '👥',
            'system': '⚙️',
            'file': '📎',
            'voice': '🎤'
        };
        return icons[type] || '🔔';
    }

    async markNotificationRead(notificationId) {
        try {
            await NotificationsAPI.markAsRead(notificationId);
            this.loadNotifications();
        } catch (error) {
            Utils.showError('Failed to mark as read: ' + error.message);
        }
    }

    async deleteNotification(notificationId) {
        try {
            await NotificationsAPI.deleteNotification(notificationId);
            this.loadNotifications();
        } catch (error) {
            Utils.showError('Failed to delete notification: ' + error.message);
        }
    }

    // ==========================================
    // PROFILE METHODS
    // ==========================================
    async loadProfile() {
        try {
            const result = await UsersAPI.getProfile();
            const user = result.profile || result.user;
            const stats = await UsersAPI.getStats();
            
            document.getElementById('profile-content').innerHTML = `
                <div class="profile-avatar-section">
                    <img src="${user.profile_picture || 'assets/images/default-avatar.png'}" alt="${user.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                    <h2 style="margin-top:12px;">${Utils.escapeHTML(user.full_name || user.username)}</h2>
                    <p style="color:var(--text-secondary);">@${Utils.escapeHTML(user.username)}</p>
                    <p style="font-size:13px;color:var(--text-secondary);">${user.online_status || 'Offline'}</p>
                </div>
                <div class="profile-info-grid">
                    <div class="profile-info-item">
                        <label>Email</label>
                        <p>${Utils.escapeHTML(user.email)}</p>
                    </div>
                    <div class="profile-info-item">
                        <label>Bio</label>
                        <p>${Utils.escapeHTML(user.bio || 'No bio yet')}</p>
                    </div>
                    <div class="profile-info-item">
                        <label>Joined</label>
                        <p>${new Date(user.created_at).toLocaleDateString()}</p>
                    </div>
                    <div class="profile-info-item">
                        <label>Last Active</label>
                        <p>${user.last_seen ? Utils.formatDate(user.last_seen) : 'Never'}</p>
                    </div>
                </div>
                <div class="profile-actions">
                    <button class="btn-primary" onclick="app.openEditProfile()">✏️ Edit Profile</button>
                    <button class="btn-secondary" onclick="app.openChangePassword()">🔒 Change Password</button>
                    <button class="btn-danger" onclick="app.logout()">🚪 Logout</button>
                </div>
                <div style="margin-top:20px;border-top:1px solid var(--divider);padding-top:20px;">
                    <h3 style="margin-bottom:12px;">Statistics</h3>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;">
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.stats?.friend_count || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Friends</div>
                        </div>
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.stats?.group_count || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Groups</div>
                        </div>
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.stats?.total_messages_sent || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Messages</div>
                        </div>
                    </div>
                </div>
            `;
        } catch (error) {
            Utils.showError('Failed to load profile: ' + error.message);
        }
    }

    // ==========================================
    // SETTINGS METHODS
    // ==========================================
    renderSettings() {
        document.getElementById('settings-content').innerHTML = `
            <div class="settings-section">
                <h3>Appearance</h3>
                <div class="settings-item">
                    <div>
                        <div>Dark Mode</div>
                        <div style="font-size:13px;color:var(--text-secondary);">Toggle dark/light theme</div>
                    </div>
                    <button class="btn-secondary" onclick="app.toggleTheme()">${document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️ Light' : '🌙 Dark'}</button>
                </div>
            </div>
            <div class="settings-section">
                <h3>Notifications</h3>
                <div class="settings-item">
                    <div>
                        <div>Push Notifications</div>
                        <div style="font-size:13px;color:var(--text-secondary);">Enable browser notifications</div>
                    </div>
                    <button class="btn-secondary" onclick="app.toggleNotifications()">${'Notification' in window && Notification.permission === 'granted' ? '✅ Enabled' : '🔔 Enable'}</button>
                </div>
            </div>
            <div class="settings-section">
                <h3>Security</h3>
                <div class="settings-item">
                    <div>
                        <div>Change Password</div>
                        <div style="font-size:13px;color:var(--text-secondary);">Update your account password</div>
                    </div>
                    <button class="btn-secondary" onclick="app.openChangePassword()">Change</button>
                </div>
                <div class="settings-item">
                    <div>
                        <div>Session</div>
                        <div style="font-size:13px;color:var(--text-secondary);">Log out from all devices</div>
                    </div>
                    <button class="btn-danger" onclick="app.logoutAllDevices()">Logout All</button>
                </div>
            </div>
            <div class="settings-section">
                <h3>About</h3>
                <div class="settings-item">
                    <div>
                        <div>Version</div>
                        <div style="font-size:13px;color:var(--text-secondary);">Secure Chat v1.0.0</div>
                    </div>
                </div>
                <div class="settings-item">
                    <div>
                        <div>Encryption</div>
                        <div style="font-size:13px;color:var(--text-secondary);">AES-256-GCM + RSA-2048</div>
                    </div>
                </div>
            </div>
        `;
    }

    toggleTheme() {
        const dark = document.documentElement.getAttribute('data-theme') === 'dark';
        if (dark) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
        }
        this.renderSettings();
    }

    toggleNotifications() {
        if ('Notification' in window) {
            if (Notification.permission === 'granted') {
                Utils.showToast('Notifications already enabled', 'info');
            } else if (Notification.permission === 'denied') {
                Utils.showToast('Please enable notifications in your browser settings', 'error');
            } else {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        Utils.showToast('Notifications enabled!', 'success');
                    } else {
                        Utils.showToast('Notifications disabled', 'info');
                    }
                    this.renderSettings();
                });
            }
        }
    }

    async logoutAllDevices() {
        if (!confirm('Logout from all devices?')) return;
        try {
            await AuthAPI.logout();
            Utils.showToast('Logged out from all devices', 'info');
            this.logout();
        } catch (error) {
            Utils.showError('Failed to logout all devices: ' + error.message);
        }
    }

    // ==========================================
    // MODAL METHODS
    // ==========================================
    openModal(title, content) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = content;
        document.getElementById('modal-overlay').style.display = 'flex';
        
        // Re-run any scripts in the modal content
        const scripts = document.getElementById('modal-body').querySelectorAll('script');
        scripts.forEach(oldScript => {
            const newScript = document.createElement('script');
            Array.from(oldScript.attributes).forEach(attr => {
                newScript.setAttribute(attr.name, attr.value);
            });
            newScript.textContent = oldScript.textContent;
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });
    }

    closeModal() {
        document.getElementById('modal-overlay').style.display = 'none';
        document.getElementById('modal-body').innerHTML = '';
    }

    // ==========================================
    // UTILITY METHODS
    // ==========================================
    insertEmoji(emoji) {
        const input = document.getElementById('message-input');
        input.value += emoji;
        input.focus();
        document.getElementById('emoji-picker').style.display = 'none';
    }

    getAddFriendModal() {
        return `
            <p>Search for users by username or email to add them as friends.</p>
            <div style="margin-top:16px;">
                <input type="text" id="modal-friend-search" placeholder="Search for users..." style="width:100%;padding:10px 14px;border:2px solid var(--border);border-radius:var(--radius);font-size:14px;" />
                <div id="modal-friend-results" style="margin-top:12px;"></div>
            </div>
        `;
    }

    getCreateGroupModal() {
        return `
            <form id="create-group-form">
                <div class="form-group">
                    <label for="group-name">Group Name</label>
                    <input type="text" id="group-name" placeholder="Enter group name" required />
                </div>
                <div class="form-group">
                    <label for="group-description">Description</label>
                    <input type="text" id="group-description" placeholder="What's this group about?" />
                </div>
                <div class="form-group">
                    <label>Add Members</label>
                    <div id="group-member-search">
                        <input type="text" id="group-member-input" placeholder="Search friends..." style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px;" />
                        <div id="group-member-results" style="margin-top:8px;max-height:150px;overflow-y:auto;"></div>
                    </div>
                </div>
                <div style="display:flex;gap:8px;margin-top:16px;">
                    <button type="submit" class="btn-primary">Create Group</button>
                    <button type="button" class="btn-secondary" onclick="closeModal()">Cancel</button>
                </div>
            </form>
        `;
    }

    getNewChatModalContent() {
        return `
            <p>Start a new conversation</p>
            <div style="margin-top:16px;">
                <input type="text" id="new-chat-search" placeholder="Search for users..." style="width:100%;padding:10px 14px;border:2px solid var(--border);border-radius:var(--radius);font-size:14px;" />
                <div id="new-chat-results" style="margin-top:12px;"></div>
            </div>
        `;
    }

    getChatSearchModal() {
        return `
            <div>
                <div class="search-bar">
                    <input type="text" id="message-search-input" placeholder="Search in this chat..." />
                    <span class="search-icon">🔍</span>
                </div>
                <div id="message-search-results" style="margin-top:12px;max-height:300px;overflow-y:auto;"></div>
            </div>
        `;
    }

    // ==========================================
    // FILE UPLOAD
    // ==========================================
    openFileUpload() {
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = 'image/*,application/pdf,application/msword,text/plain,video/mp4,audio/*,application/zip';
        input.onchange = async (e) => {
            const files = e.target.files;
            if (!files.length) return;

            const password = prompt('Enter your password to encrypt files:');
            if (!password) return;

            for (const file of files) {
                const formData = new FormData();
                formData.append('file', file);
                if (this.currentChat) formData.append('message_id', this.currentChat);
                formData.append('password', password);

                try {
                    await FilesAPI.upload(formData);
                    Utils.showToast(`Uploaded: ${file.name}`, 'success');
                    if (this.currentChat) this.loadChatMessages(this.currentChat);
                } catch (error) {
                    Utils.showError(`Failed to upload ${file.name}: ` + error.message);
                }
            }
        };
        input.click();
    }

    // ==========================================
    // VOICE RECORDING
    // ==========================================
    startVoiceRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            Utils.showError('Voice recording not supported in this browser');
            return;
        }

        const btn = document.getElementById('mic-btn');
        if (btn.classList.contains('recording')) {
            this.stopVoiceRecording();
            return;
        }

        navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
            this.mediaRecorder = new MediaRecorder(stream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                this.audioChunks.push(e.data);
            };

            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.sendVoiceMessage(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            this.mediaRecorder.start();
            btn.classList.add('recording');
            btn.textContent = '⏹️';
            Utils.showToast('Recording... Click again to stop', 'info');
        }).catch(() => {
            Utils.showError('Could not access microphone');
        });
    }

    stopVoiceRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
            const btn = document.getElementById('mic-btn');
            btn.classList.remove('recording');
            btn.textContent = '🎤';
        }
    }

    async sendVoiceMessage(audioBlob) {
        const password = prompt('Enter your password to encrypt:');
        if (!password) return;

        const formData = new FormData();
        formData.append('file', audioBlob, 'voice.webm');
        if (this.currentChat) formData.append('message_id', this.currentChat);
        formData.append('password', password);

        try {
            await FilesAPI.upload(formData);
            Utils.showToast('Voice message sent!', 'success');
            if (this.currentChat) this.loadChatMessages(this.currentChat);
        } catch (error) {
            Utils.showError('Failed to send voice message: ' + error.message);
        }
    }

    // ==========================================
    // CHAT MENU
    // ==========================================
    showChatMenu() {
        this.openModal('Chat Options', `
            <div style="display:flex;flex-direction:column;gap:8px;">
                <button class="btn-secondary" onclick="app.clearChat()">🗑️ Clear Chat</button>
                <button class="btn-danger" onclick="app.blockUser()">🚫 Block User</button>
                <button class="btn-secondary" onclick="closeModal()">Cancel</button>
            </div>
        `);
    }

    async clearChat() {
        if (!confirm('Clear all messages in this chat?')) return;
        Utils.showToast('Chat cleared', 'info');
        closeModal();
    }

    async blockUser() {
        if (!confirm('Block this user?')) return;
        try {
            await FriendsAPI.blockUser({ user_id: this.currentChat });
            Utils.showToast('User blocked', 'info');
            closeModal();
            this.switchView('chat');
        } catch (error) {
            Utils.showError('Failed to block user: ' + error.message);
        }
    }

    openGroupSettings(groupId) {
        this.openModal('Group Settings', `
            <div style="display:flex;flex-direction:column;gap:12px;">
                <button class="btn-secondary" onclick="app.leaveGroup(${groupId})">🚪 Leave Group</button>
                <button class="btn-danger" onclick="app.deleteGroup(${groupId})">🗑️ Delete Group</button>
                <button class="btn-secondary" onclick="closeModal()">Close</button>
            </div>
        `);
    }

    async leaveGroup(groupId) {
        if (!confirm('Leave this group?')) return;
        try {
            await GroupsAPI.leaveGroup(groupId);
            Utils.showToast('Left group', 'info');
            closeModal();
            this.loadGroups();
        } catch (error) {
            Utils.showError('Failed to leave group: ' + error.message);
        }
    }

    handleNewMessage(data) {
        if (this.currentChat === data.sender_id || this.currentChat === data.recipient_id) {
            this.loadChatMessages(this.currentChat);
        }
        this.loadChats();
    }

    handleTypingIndicator(data) {
        const statusEl = document.getElementById('chat-status');
        if (data.is_typing) {
            statusEl.textContent = 'Typing...';
        } else {
            this.getChatUserInfo(this.currentChat);
        }
    }

    handleUserStatus(data) {
        if (this.currentChat === data.user_id) {
            document.getElementById('chat-status').textContent = data.status || 'Offline';
        }
        if (data.user_id === this.currentUser?.id) {
            this.updateStatusIndicator(data.status);
            document.getElementById('sidebar-status-text').textContent = data.status || 'Offline';
        }
    }

    handleFriendRequest(data) {
        Utils.showToast(`New friend request from ${data.sender?.username}`, 'info');
        this.loadNotifications();
        this.loadFriends();
    }

    handleNotification(data) {
        Utils.showToast(data.message, 'info');
        this.loadNotifications();
    }

    // ==========================================
    // INITIALIZE
    // ==========================================
    static getInstance() {
        if (!window.app) {
            window.app = new SecureChatApp();
        }
        return window.app;
    }
}

// Expose app globally
window.app = SecureChatApp.getInstance();
window.closeModal = () => window.app?.closeModal();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOM ready');
    const theme = localStorage.getItem('theme');
    if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
    console.log('✅ App ready - use app.xxx() to interact');
});

// ============================================
// CONSOLE HELPERS FOR DEBUGGING
// ============================================
console.log('📖 Available commands:');
console.log('  app.login("username", "password") - Login');
console.log('  app.logout() - Logout');
console.log('  app.loadChats() - Refresh chats');
console.log('  app.loadFriends() - Refresh friends');
console.log('  app.loadGroups() - Refresh groups');
console.log('  app.loadNotifications() - Refresh notifications');
console.log('  app.loadProfile() - Refresh profile');
console.log('  app.openChat(id) - Open chat with user ID');
console.log('  app.sendMessage() - Send current message');
console.log('  app.toggleTheme() - Toggle dark/light mode');
console.log('  app.logoutAllDevices() - Logout from all devices');