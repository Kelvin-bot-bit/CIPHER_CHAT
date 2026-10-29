import Avatar from '../common/Avatar.jsx'
import { formatRelative } from '../../utils/time'

export default function ChatList({ friends, groups, activeChat, onSelect, loading, unreadByChat = {} }) {
  const items = [
    ...friends.map((f) => ({
      key: `user-${f.id}`,
      chat: { id: f.id, type: 'user', name: f.full_name || f.username, username: f.username },
      avatar: <Avatar name={f.full_name || f.username} src={f.profile_picture} status={f.online_status} />,
      subtitle:
        f.online_status === 'online' ? 'Online' : f.last_seen ? `Last seen ${formatRelative(f.last_seen)}` : 'Offline',
    })),
    ...groups.map((g) => ({
      key: `group-${g.id}`,
      chat: { id: g.id, type: 'group', name: g.group_name },
      avatar: <Avatar name={g.group_name} />,
      subtitle: `${g.member_count ?? ''} member${g.member_count === 1 ? '' : 's'}`.trim(),
    })),
  ]

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-14 animate-pulse rounded-xl bg-surface-alt" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted">
        <p className="font-display text-base text-paper">No conversations yet</p>
        <p>Add a friend or create a group to start a secure chat.</p>
      </div>
    )
  }

  // Chats with unread messages first (most-unread on top), then everything
  // else in whatever order it arrived in.
  const sorted = [...items].sort((a, b) => {
    const au = unreadByChat[`${a.chat.type}_${a.chat.id}`] || 0
    const bu = unreadByChat[`${b.chat.type}_${b.chat.id}`] || 0
    return bu - au
  })

  return (
    <ul className="flex flex-col gap-0.5 overflow-y-auto p-2">
      {sorted.map(({ key, chat, avatar, subtitle }) => {
        const active = activeChat && activeChat.type === chat.type && activeChat.id === chat.id
        const unread = unreadByChat[`${chat.type}_${chat.id}`] || 0
        return (
          <li key={key}>
            <button
              onClick={() => onSelect(chat)}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors
                ${active ? 'bg-surface-hi' : 'hover:bg-surface-alt'}`}
            >
              {avatar}
              <span className="min-w-0 flex-1">
                <span className={`block truncate text-sm ${unread > 0 ? 'font-semibold text-paper' : 'font-medium text-paper'}`}>
                  {chat.name}
                </span>
                <span className={`block truncate text-xs ${unread > 0 ? 'text-paper/70' : 'text-muted'}`}>{subtitle}</span>
              </span>
              {unread > 0 && (
                <span
                  aria-label={`${unread} unread message${unread === 1 ? '' : 's'}`}
                  className="flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded-full bg-signal px-1.5 text-[0.7rem] font-semibold text-ink"
                >
                  {unread > 99 ? '99+' : unread}
                </span>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
