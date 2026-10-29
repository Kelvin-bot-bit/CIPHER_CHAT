// ============================================
// NOTIFICATIONS HELPERS
// ============================================

const NotificationsHelpers = {
    // Get notification icon
    getIcon(type) {
        const icons = {
            'message': '💬',
            'friend_request': '👤',
            'group_invite': '👥',
            'system': '⚙️',
            'file': '📎',
            'voice': '🎤'
        };
        return icons[type] || '🔔';
    },

    // Get notification type label
    getTypeLabel(type) {
        const labels = {
            'message': 'New Message',
            'friend_request': 'Friend Request',
            'group_invite': 'Group Invite',
            'system': 'System',
            'file': 'File Shared',
            'voice': 'Voice Message'
        };
        return labels[type] || 'Notification';
    },

    // Render notification item
    renderNotification(notification) {
        return `
            <div class="notification-item ${notification.is_read ? '' : 'unread'}" data-notif-id="${notification.id}">
                <div class="notif-icon">${this.getIcon(notification.notification_type)}</div>
                <div class="notif-content">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:12px;font-weight:500;color:var(--text-secondary);">${this.getTypeLabel(notification.notification_type)}</span>
                        <span style="font-size:12px;color:var(--text-secondary);">${Utils.formatDate(notification.created_at)}</span>
                    </div>
                    <div class="notif-message">${Utils.escapeHTML(notification.message)}</div>
                    ${notification.sender ? `<div style="font-size:12px;color:var(--text-secondary);">From: ${Utils.escapeHTML(notification.sender.username)}</div>` : ''}
                </div>
                ${!notification.is_read ? `<button class="btn-secondary" onclick="app.markNotificationRead(${notification.id})">✓</button>` : ''}
                <button class="btn-danger" onclick="app.deleteNotification(${notification.id})">✕</button>
            </div>
        `;
    },

    // Get unread count display
    getUnreadDisplay(count) {
        if (count === 0) return '🔔';
        if (count > 99) return '🔔 (99+)';
        return `🔔 (${count})`;
    },

    // Get notification count display
    getCountDisplay(count) {
        if (count === 0) return 'No notifications';
        if (count === 1) return '1 notification';
        return `${count} notifications`;
    }
};

// Make NotificationsHelpers globally available
window.NotificationsHelpers = NotificationsHelpers;