// ============================================
// GROUPS HELPERS
// ============================================

const GroupsHelpers = {
    // Get group role display
    getRoleDisplay(role) {
        const roleMap = {
            admin: '👑 Admin',
            moderator: '🛡️ Moderator',
            member: '👤 Member',
        };
        return roleMap[role] || '👤 Member';
    },

    // Render group card
    renderGroupCard(group) {
        return `
            <div class="group-card" onclick="app.openGroupChat(${group.id})">
                <img src="${group.group_picture || 'assets/images/default-avatar.png'}" alt="${group.group_name}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                <div class="group-info">
                    <div class="group-name">${Utils.escapeHTML(group.group_name)}</div>
                    <div class="group-members">👥 ${group.member_count || 0} members</div>
                    ${group.group_description ? `<div style="font-size:13px;color:var(--text-secondary);">${Utils.escapeHTML(group.group_description)}</div>` : ''}
                </div>
                <div style="display:flex;gap:8px;">
                    <button class="btn-secondary" onclick="event.stopPropagation();app.openGroupSettings(${group.id})">⚙️</button>
                    <button class="btn-danger" onclick="event.stopPropagation();app.deleteGroup(${group.id})">✕</button>
                </div>
            </div>
        `;
    },

    // Render group member
    renderMember(member) {
        return `
            <div style="display:flex;align-items:center;gap:12px;padding:8px 12px;border-bottom:1px solid var(--divider);">
                <img src="${member.profile_picture || 'assets/images/default-avatar.png'}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22%3E%3Cdefs%3E%3ClinearGradient id=%22g%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 stop-color=%22%2342a5f5%22/%3E%3Cstop offset=%22100%25%22 stop-color=%22%237b1fa2%22/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx=%22100%22 cy=%22100%22 r=%2295%22 fill=%22%23e3f2fd%22/%3E%3Ccircle cx=%22100%22 cy=%2275%22 r=%2235%22 fill=%22url(%23g)%22/%3E%3Cellipse cx=%22100%22 cy=%22165%22 rx=%2255%22 ry=%2235%22 fill=%22url(%23g)%22 opacity=%220.8%22/%3E%3Ccircle cx=%2285%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Ccircle cx=%22115%22 cy=%2270%22 r=%224%22 fill=%22white%22 opacity=%220.6%22/%3E%3Cpath d=%22M90 90 Q100 100 110 90%22 stroke=%22white%22 stroke-width=%222%22 fill=%22none%22 opacity=%220.6%22/%3E%3C/svg%3E'" />
                <div style="flex:1;">
                    <div>${Utils.escapeHTML(member.full_name || member.username)}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">${this.getRoleDisplay(member.role)}</div>
                </div>
                ${member.role !== 'admin' ? `<button class="btn-danger" onclick="app.removeGroupMember(${member.user_id})">✕</button>` : ''}
            </div>
        `;
    },

    // Get group member count display
    getMemberCountDisplay(count) {
        if (count === 0) return 'No members';
        if (count === 1) return '1 member';
        return `${count} members`;
    },

    // Check if user is group admin
    isGroupAdmin(group, userId) {
        if (!group || !group.members) return false;
        const member = group.members.find(m => m.user_id === userId);
        return member && member.role === 'admin';
    },

    // Get group initial for avatar
    getGroupInitial(name) {
        if (!name) return 'G';
        return name.charAt(0).toUpperCase();
    }
};

// Make GroupsHelpers globally available
window.GroupsHelpers = GroupsHelpers;