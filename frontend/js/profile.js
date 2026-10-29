// ============================================
// PROFILE HELPERS
// ============================================

const ProfileHelpers = {
    // Format profile data for display
    formatProfile(user) {
        return {
            ...user,
            displayName: user.full_name || user.username,
            joinedDate: new Date(user.created_at).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
            }),
            lastActive: user.last_seen ? Utils.formatDate(user.last_seen) : 'Never',
            statusDisplay: this.getStatusDisplay(user.online_status),
        };
    },

    // Get status display
    getStatusDisplay(status) {
        const statusMap = {
            online: '🟢 Online',
            offline: '⚪ Offline',
            away: '🟡 Away',
            busy: '🔴 Busy',
        };
        return statusMap[status] || '⚪ Offline';
    },

    // Render profile card
    renderProfile(user, stats) {
        const formatted = this.formatProfile(user);
        return `
            <div class="profile-avatar-section">
                <img src="${user.profile_picture || 'assets/images/default-avatar.png'}" alt="${user.username}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                <h2 style="margin-top:12px;">${Utils.escapeHTML(formatted.displayName)}</h2>
                <p style="color:var(--text-secondary);">@${Utils.escapeHTML(user.username)}</p>
                <p style="font-size:13px;color:var(--text-secondary);">${formatted.statusDisplay}</p>
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
                    <p>${formatted.joinedDate}</p>
                </div>
                <div class="profile-info-item">
                    <label>Last Active</label>
                    <p>${formatted.lastActive}</p>
                </div>
                <div class="profile-info-item">
                    <label>Verified</label>
                    <p>${user.is_verified ? '✅ Yes' : '❌ No'}</p>
                </div>
                <div class="profile-info-item">
                    <label>Account Status</label>
                    <p>${user.is_active ? '✅ Active' : '❌ Inactive'}</p>
                </div>
            </div>
            <div class="profile-actions">
                <button class="btn-primary" onclick="app.openEditProfile()">✏️ Edit Profile</button>
                <button class="btn-secondary" onclick="app.openChangePassword()">🔒 Change Password</button>
                <button class="btn-danger" onclick="app.logout()">🚪 Logout</button>
            </div>
            ${stats ? `
                <div style="margin-top:20px;border-top:1px solid var(--divider);padding-top:20px;">
                    <h3 style="margin-bottom:12px;">Statistics</h3>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;">
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.friend_count || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Friends</div>
                        </div>
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.group_count || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Groups</div>
                        </div>
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.total_messages_sent || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Messages</div>
                        </div>
                        <div class="text-center" style="background:var(--background);padding:12px;border-radius:var(--radius);">
                            <div style="font-size:24px;font-weight:700;color:var(--primary);">${stats.unread_messages || 0}</div>
                            <div style="font-size:13px;color:var(--text-secondary);">Unread</div>
                        </div>
                    </div>
                </div>
            ` : ''}
        `;
    },

    // Get user initials for avatar
    getInitials(name) {
        if (!name) return '?';
        const parts = name.split(' ');
        if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
        return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
    },

    // Validate profile data
    validateProfileData(data) {
        const errors = {};
        if (data.full_name && data.full_name.length > 100) {
            errors.full_name = 'Full name must be less than 100 characters';
        }
        if (data.bio && data.bio.length > 500) {
            errors.bio = 'Bio must be less than 500 characters';
        }
        return {
            valid: Object.keys(errors).length === 0,
            errors: errors
        };
    },

    // Get profile completion percentage
    getProfileCompletion(user) {
        let total = 0;
        let filled = 0;
        const fields = ['profile_picture', 'full_name', 'bio', 'email', 'phone'];
        fields.forEach(field => {
            total++;
            if (user[field] && user[field] !== '') filled++;
        });
        return Math.round((filled / total) * 100);
    }
};

// Make ProfileHelpers globally available
window.ProfileHelpers = ProfileHelpers;