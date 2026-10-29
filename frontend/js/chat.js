// ============================================
// CHAT HELPERS
// ============================================

const ChatHelpers = {
    // Format messages for display
    formatMessage(message) {
        return {
            ...message,
            formattedTime: Utils.formatTime(message.created_at),
            isOwn: message.sender_id === window.app?.currentUser?.id,
        };
    },

    // Group messages by date
    groupByDate(messages) {
        const groups = {};
        messages.forEach(msg => {
            const date = new Date(msg.created_at).toDateString();
            if (!groups[date]) groups[date] = [];
            groups[date].push(msg);
        });
        return groups;
    },

    // Get message status icon
    getStatusIcon(message) {
        if (message.is_deleted) return '🗑️';
        if (message.is_edited) return '📝';
        if (message.is_valid_signature === false) return '⚠️';
        return '';
    },

    // Render message with reactions
    renderMessage(message) {
        const formatted = this.formatMessage(message);
        const reactions = message.reactions ? Object.entries(message.reactions) : [];
        return `
            <div class="message ${formatted.isOwn ? 'sent' : 'received'}">
                <div class="msg-text">${Utils.escapeHTML(message.message)}</div>
                <div class="msg-meta">
                    <span class="msg-time">${formatted.formattedTime}</span>
                    ${this.getStatusIcon(message)}
                    ${message.is_read ? '✓✓' : '✓'}
                </div>
                ${reactions.length ? `
                    <div style="display:flex;gap:4px;margin-top:4px;flex-wrap:wrap;">
                        ${reactions.map(([emoji, users]) => `
                            <span style="background:var(--background);padding:2px 8px;border-radius:12px;font-size:12px;">
                                ${emoji} ${users.length}
                            </span>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;
    },

    // Get chat user display name
    getUserDisplayName(user) {
        return user?.full_name || user?.username || 'Unknown User';
    },

    // Get chat user status
    getUserStatus(user) {
        const statusMap = {
            online: '🟢 Online',
            offline: '⚪ Offline',
            away: '🟡 Away',
            busy: '🔴 Busy',
        };
        return statusMap[user?.online_status] || '⚪ Offline';
    },

    // Create chat list item HTML
    createChatListItem(chat) {
        return `
            <div class="chat-list-item" data-chat-id="${chat.id}">
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
        `;
    },

    // Get typing text
    getTypingText(users) {
        if (!users || users.length === 0) return '';
        if (users.length === 1) return `${users[0]} is typing...`;
        if (users.length === 2) return `${users[0]} and ${users[1]} are typing...`;
        return `${users[0]} and ${users.length - 1} others are typing...`;
    }
};

// Make ChatHelpers globally available
window.ChatHelpers = ChatHelpers;