// ============================================
// FRIENDS HELPERS
// ============================================

const FriendsHelpers = {
    // Get friend status display
    getStatusDisplay(status) {
        const statusMap = {
            online: '🟢 Online',
            offline: '⚪ Offline',
            away: '🟡 Away',
            busy: '🔴 Busy',
        };
        return statusMap[status] || '⚪ Offline';
    },

    // Check if user is friend
    isFriend(friendsList, userId) {
        return friendsList.some(f => f.id === userId);
    },

    // Get friend request status
    getRequestStatus(status) {
        const statusMap = {
            pending: '⏳ Pending',
            accepted: '✅ Accepted',
            rejected: '❌ Rejected',
            cancelled: '🚫 Cancelled',
        };
        return statusMap[status] || status;
    },

    // Render friend card
    renderFriendCard(friend, actions = true) {
        return `
            <div class="friend-card">
                <img src="${friend.profile_picture || 'assets/images/default-avatar.png'}" alt="${friend.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                <div class="friend-info">
                    <div class="friend-name">${Utils.escapeHTML(friend.full_name || friend.username)}</div>
                    <div class="friend-username">@${Utils.escapeHTML(friend.username)}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">${this.getStatusDisplay(friend.online_status)}</div>
                </div>
                ${actions ? `
                    <div class="friend-actions">
                        <button class="btn-secondary" onclick="app.openChat(${friend.id})">💬</button>
                        <button class="btn-danger" onclick="app.removeFriend(${friend.id})">✕</button>
                    </div>
                ` : ''}
            </div>
        `;
    },

    // Render friend request card
    renderRequestCard(request) {
        const sender = request.sender || {};
        return `
            <div class="friend-request-card" data-request-id="${request.id}">
                <div class="request-info">
                    <img src="${sender.profile_picture || 'assets/images/default-avatar.png'}" alt="${sender.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                    <div>
                        <div>${Utils.escapeHTML(sender.full_name || sender.username)}</div>
                        <div style="font-size:13px;color:var(--text-secondary);">@${Utils.escapeHTML(sender.username)}</div>
                        ${request.message ? `<div style="font-size:13px;color:var(--text-secondary);">"${Utils.escapeHTML(request.message)}"</div>` : ''}
                    </div>
                </div>
                <div class="request-actions">
                    <button class="btn-primary" onclick="app.acceptFriendRequest(${request.id})">Accept</button>
                    <button class="btn-danger" onclick="app.rejectFriendRequest(${request.id})">Reject</button>
                </div>
            </div>
        `;
    },

    // Get friend count display
    getFriendCountDisplay(count) {
        if (count === 0) return 'No friends yet';
        if (count === 1) return '1 friend';
        return `${count} friends`;
    }
};

// Make FriendsHelpers globally available
window.FriendsHelpers = FriendsHelpers;