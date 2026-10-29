// ============================================
// API CLIENT
// ============================================

const API = {
    baseURL: localStorage.getItem('api_url') || 'http://127.0.0.1:5000/api',
    token: localStorage.getItem('access_token'),

    setToken(token) {
        this.token = token;
        if (token) {
            localStorage.setItem('access_token', token);
        } else {
            localStorage.removeItem('access_token');
        }
    },

    getHeaders() {
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        };
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        return headers;
    },

    async request(method, endpoint, data = null, isFormData = false) {
        const url = `${this.baseURL}${endpoint}`;
        const options = {
            method,
            headers: isFormData ? {} : this.getHeaders(),
            credentials: 'include',
            mode: 'cors',
        };
        
        if (data) {
            if (isFormData) {
                options.body = data;
            } else {
                options.body = JSON.stringify(data);
            }
        }

        try {
            const response = await fetch(url, options);
            
            // Handle empty responses
            const contentType = response.headers.get('content-type');
            let result;
            if (contentType && contentType.includes('application/json')) {
                result = await response.json();
            } else {
                result = await response.text();
                try {
                    result = JSON.parse(result);
                } catch {
                    // If not JSON, return as is
                }
            }
            
            if (!response.ok) {
                // Handle token expiration
                if (response.status === 401) {
                    const refreshToken = localStorage.getItem('refresh_token');
                    if (refreshToken) {
                        try {
                            const refreshResponse = await this.request('POST', '/auth/refresh', { refresh_token: refreshToken });
                            if (refreshResponse.access_token) {
                                this.setToken(refreshResponse.access_token);
                                // Retry original request
                                return this.request(method, endpoint, data, isFormData);
                            }
                        } catch (e) {
                            console.error('Token refresh failed:', e);
                            localStorage.clear();
                            this.setToken(null);
                            window.location.hash = 'login';
                            throw new Error('Session expired. Please login again.');
                        }
                    } else {
                        localStorage.clear();
                        this.setToken(null);
                        window.location.hash = 'login';
                        throw new Error('Session expired. Please login again.');
                    }
                }
                throw new Error(result.error || result.message || result || 'Request failed');
            }
            
            return result;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    get(endpoint) {
        return this.request('GET', endpoint);
    },

    post(endpoint, data, isFormData = false) {
        return this.request('POST', endpoint, data, isFormData);
    },

    put(endpoint, data) {
        return this.request('PUT', endpoint, data);
    },

    delete(endpoint, data = null) {
        return this.request('DELETE', endpoint, data);
    },

    patch(endpoint, data) {
        return this.request('PATCH', endpoint, data);
    }
};

// ============================================
// AUTH API
// ============================================

const AuthAPI = {
    register(data) {
        return API.post('/auth/register', data);
    },
    login(data) {
        return API.post('/auth/login', data);
    },
    logout() {
        return API.post('/auth/logout');
    },
    refresh(data) {
        return API.post('/auth/refresh', data);
    },
    getProfile() {
        return API.get('/users/profile');
    },
    updateProfile(data) {
        return API.put('/users/profile', data);
    },
    changePassword(data) {
        return API.post('/auth/change-password', data);
    },
    verifyEmail(userId) {
        return API.get(`/auth/verify-email/${userId}`);
    },
    forgotPassword(data) {
        return API.post('/auth/forgot-password', data);
    },
    resetPassword(data) {
        return API.post('/auth/reset-password', data);
    }
};

// ============================================
// MESSAGES API
// ============================================

const MessagesAPI = {
    send(data) {
        return API.post('/messages/send', data);
    },
    getMessages(chatId, params) {
        const query = new URLSearchParams(params).toString();
        return API.get(`/messages/chat/${chatId}${query ? '?' + query : ''}`);
    },
    edit(messageId, data) {
        return API.put(`/messages/${messageId}`, data);
    },
    delete(messageId, data) {
        return API.delete(`/messages/${messageId}`, data);
    },
    addReaction(messageId, data) {
        return API.post(`/messages/${messageId}/reaction`, data);
    },
    getUnread() {
        return API.get('/messages/unread');
    },
    markAsRead(messageId) {
        return API.post(`/messages/${messageId}/read`);
    },
    getConversation(userId) {
        return API.get(`/messages/conversation/${userId}`);
    },
    searchMessages(chatId, query) {
        return API.get(`/messages/search/${chatId}?query=${encodeURIComponent(query)}`);
    },
    pinMessage(messageId) {
        return API.post(`/messages/${messageId}/pin`);
    },
    unpinMessage(messageId) {
        return API.delete(`/messages/${messageId}/pin`);
    },
    starMessage(messageId) {
        return API.post(`/messages/${messageId}/star`);
    },
    unstarMessage(messageId) {
        return API.delete(`/messages/${messageId}/star`);
    }
};

// ============================================
// FRIENDS API
// ============================================

const FriendsAPI = {
    sendRequest(data) {
        return API.post('/friends/request', data);
    },
    acceptRequest(requestId) {
        return API.post(`/friends/request/${requestId}/accept`);
    },
    rejectRequest(requestId) {
        return API.post(`/friends/request/${requestId}/reject`);
    },
    cancelRequest(requestId) {
        return API.post(`/friends/request/${requestId}/cancel`);
    },
    removeFriend(friendId) {
        return API.delete(`/friends/${friendId}`);
    },
    blockUser(data) {
        return API.post('/friends/block', data);
    },
    unblockUser(data) {
        return API.post('/friends/unblock', data);
    },
    getFriends() {
        return API.get('/friends/list');
    },
    getRequests() {
        return API.get('/friends/requests');
    },
    getBlocked() {
        return API.get('/friends/blocked');
    },
    searchUsers(query) {
        return API.get(`/friends/search?query=${encodeURIComponent(query)}`);
    },
    getSuggestions() {
        return API.get('/friends/suggestions');
    }
};

// ============================================
// GROUPS API
// ============================================

const GroupsAPI = {
    create(data) {
        return API.post('/groups/', data);
    },
    getGroup(groupId) {
        return API.get(`/groups/${groupId}`);
    },
    getMyGroups() {
        return API.get('/groups/my-groups');
    },
    updateGroup(groupId, data) {
        return API.put(`/groups/${groupId}`, data);
    },
    addMember(groupId, data) {
        return API.post(`/groups/${groupId}/members`, data);
    },
    removeMember(groupId, userId) {
        return API.delete(`/groups/${groupId}/members/${userId}`);
    },
    promoteToAdmin(groupId, userId) {
        return API.post(`/groups/${groupId}/promote/${userId}`);
    },
    demoteFromAdmin(groupId, userId) {
        return API.post(`/groups/${groupId}/demote/${userId}`);
    },
    leaveGroup(groupId) {
        return API.post(`/groups/${groupId}/leave`);
    },
    deleteGroup(groupId) {
        return API.delete(`/groups/${groupId}`);
    },
    getMembers(groupId) {
        return API.get(`/groups/${groupId}/members`);
    },
    getGroupMessages(groupId, params) {
        const query = new URLSearchParams(params).toString();
        return API.get(`/groups/${groupId}/messages${query ? '?' + query : ''}`);
    }
};

// ============================================
// FILES API
// ============================================

const FilesAPI = {
    upload(formData, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const url = `${API.baseURL}/files/upload`;
            
            xhr.open('POST', url);
            xhr.withCredentials = true;
            xhr.setRequestHeader('Authorization', `Bearer ${API.token}`);
            
            if (onProgress) {
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        onProgress(e.loaded / e.total);
                    }
                });
            }
            
            xhr.onload = () => {
                try {
                    const response = JSON.parse(xhr.responseText);
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(response);
                    } else {
                        reject(new Error(response.error || 'Upload failed'));
                    }
                } catch (e) {
                    reject(new Error('Invalid response from server'));
                }
            };
            
            xhr.onerror = () => {
                reject(new Error('Network error occurred'));
            };
            
            xhr.send(formData);
        });
    },
    download(fileId, password) {
        return API.get(`/files/download/${fileId}?password=${encodeURIComponent(password)}`);
    },
    preview(fileId) {
        return API.get(`/files/preview/${fileId}`);
    },
    stream(fileId) {
        return API.get(`/files/stream/${fileId}`);
    },
    delete(fileId) {
        return API.delete(`/files/${fileId}`);
    },
    getMyFiles() {
        return API.get('/files/my-files');
    },
    getUserFiles(userId) {
        return API.get(`/files/user/${userId}`);
    },
    getMessageFiles(messageId) {
        return API.get(`/files/message/${messageId}`);
    },
    updateFile(fileId, data) {
        return API.put(`/files/${fileId}`, data);
    },
    getShareLink(fileId) {
        return API.get(`/files/${fileId}/share`);
    }
};

// ============================================
// USERS API
// ============================================

const UsersAPI = {
    getProfile() {
        return API.get('/users/profile');
    },
    updateProfile(data) {
        return API.put('/users/profile', data);
    },
    getUser(userId) {
        return API.get(`/users/${userId}`);
    },
    searchUsers(query) {
        return API.get(`/users/search?query=${encodeURIComponent(query)}`);
    },
    updateStatus(data) {
        return API.put('/users/status', data);
    },
    getStats() {
        return API.get('/users/stats');
    },
    getOnlineUsers() {
        return API.get('/users/online');
    },
    getRecentUsers(limit = 10) {
        return API.get(`/users/recent?limit=${limit}`);
    },
    getContacts() {
        return API.get('/users/contacts');
    },
    getCurrentUser() {
        return API.get('/users/me');
    },
    getSettings() {
        return API.get('/users/settings');
    },
    updateSettings(data) {
        return API.put('/users/settings', data);
    },
    deleteAccount() {
        return API.delete('/users/account');
    }
};

// ============================================
// NOTIFICATIONS API
// ============================================

const NotificationsAPI = {
    getNotifications(params) {
        const query = params ? new URLSearchParams(params).toString() : '';
        return API.get(`/notifications${query ? '?' + query : ''}`);
    },
    getUnreadCount() {
        return API.get('/notifications/unread');
    },
    markAsRead(notificationId) {
        return API.put(`/notifications/${notificationId}/read`);
    },
    markAllAsRead() {
        return API.put('/notifications/read-all');
    },
    deleteNotification(notificationId) {
        return API.delete(`/notifications/${notificationId}`);
    },
    getPreferences() {
        return API.get('/notifications/preferences');
    },
    updatePreferences(data) {
        return API.put('/notifications/preferences', data);
    },
    getTypes() {
        return API.get('/notifications/types');
    }
};

// ============================================
// ADMIN API (for admin users only)
// ============================================

const AdminAPI = {
    getUsers(params) {
        const query = params ? new URLSearchParams(params).toString() : '';
        return API.get(`/admin/users${query ? '?' + query : ''}`);
    },
    updateUser(userId, data) {
        return API.put(`/admin/users/${userId}`, data);
    },
    deleteUser(userId) {
        return API.delete(`/admin/users/${userId}`);
    },
    getStatistics() {
        return API.get('/admin/statistics');
    },
    getAuditLogs(params) {
        const query = params ? new URLSearchParams(params).toString() : '';
        return API.get(`/admin/audit-logs${query ? '?' + query : ''}`);
    },
    getSystemStatus() {
        return API.get('/admin/system-status');
    }
};

// ============================================
// MAKE APIS GLOBALLY AVAILABLE
// ============================================

window.API = API;
window.AuthAPI = AuthAPI;
window.MessagesAPI = MessagesAPI;
window.FriendsAPI = FriendsAPI;
window.GroupsAPI = GroupsAPI;
window.FilesAPI = FilesAPI;
window.UsersAPI = UsersAPI;
window.NotificationsAPI = NotificationsAPI;
window.AdminAPI = AdminAPI;

console.log('✅ API Client initialized');
console.log('📡 API URL:', API.baseURL);
console.log('🔑 Token:', API.token ? 'Present' : 'Not set');