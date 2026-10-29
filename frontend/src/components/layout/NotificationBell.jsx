import { useState } from 'react'
import { useNotifications } from '../../context/NotificationContext.jsx'
import { formatRelative } from '../../utils/time'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'

export default function NotificationBell() {
  const { notifications, unreadCount, loading, markAsRead, markAllAsRead, dismiss, label } = useNotifications()
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        className="relative rounded-full p-1.5 text-muted hover:bg-surface-alt hover:text-paper"
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-danger px-1 text-[0.62rem] font-semibold text-paper">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <button aria-hidden="true" tabIndex={-1} onClick={() => setOpen(false)} className="fixed inset-0 z-40 cursor-default" />
          <div className="absolute right-0 top-9 z-50 w-80 overflow-hidden rounded-xl border border-line bg-surface-hi shadow-2xl">
            <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
              <p className="text-sm font-medium text-paper">Notifications</p>
              {unreadCount > 0 && (
                <button onClick={markAllAsRead} className="text-xs font-medium text-signal hover:underline">
                  Mark all read
                </button>
              )}
            </div>

            <div className="max-h-80 overflow-y-auto">
              {loading ? (
                <div className="flex justify-center py-6">
                  <Spinner size={16} />
                </div>
              ) : notifications.length === 0 ? (
                <p className="px-3.5 py-8 text-center text-sm text-muted">You're all caught up.</p>
              ) : (
                <ul>
                  {notifications.map((n) => (
                    <li
                      key={n.id}
                      className={`flex items-start gap-2.5 border-b border-line/60 px-3.5 py-2.5 last:border-b-0 ${!n.is_read ? 'bg-signal-dim/10' : ''}`}
                    >
                      <Avatar name={n.sender?.full_name || n.sender?.username || '?'} src={n.sender?.profile_picture} size={30} />
                      <button onClick={() => !n.is_read && markAsRead(n.id)} className="min-w-0 flex-1 text-left">
                        <p className={`text-sm leading-snug ${n.is_read ? 'text-muted' : 'text-paper'}`}>{label(n)}</p>
                        <p className="mt-0.5 text-[0.7rem] text-muted">{formatRelative(n.created_at)}</p>
                      </button>
                      <div className="flex shrink-0 flex-col items-center gap-1">
                        {!n.is_read && <span className="h-1.5 w-1.5 rounded-full bg-signal" aria-label="Unread" />}
                        <button
                          onClick={() => dismiss(n.id)}
                          aria-label="Dismiss notification"
                          className="text-muted hover:text-paper"
                        >
                          ✕
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function BellIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
