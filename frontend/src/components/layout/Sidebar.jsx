import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useTheme } from '../../context/ThemeContext.jsx'
import Avatar from '../common/Avatar.jsx'
import NotificationBell from './NotificationBell.jsx'

const TABS = [
  { key: 'chats', label: 'Chats' },
  { key: 'status', label: 'Status' },
  { key: 'friends', label: 'Friends' },
  { key: 'groups', label: 'Groups' },
  { key: 'files', label: 'Files' },
]

export default function Sidebar({ tab, onTabChange, onOpenProfile, chatsBadge = 0, children }) {
  const { user, lock, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()

  return (
    <div className="flex h-full w-full flex-col border-r border-line bg-surface lg:w-[22rem]">
      <div className="flex items-center gap-2 px-4 py-3.5">
        <span className="font-display text-lg font-semibold text-paper">Cipher</span>
        <span className="ml-auto flex items-center gap-1 rounded-full bg-signal-dim px-2 py-0.5 text-[0.65rem] font-medium text-signal">
          <span className="h-1.5 w-1.5 rounded-full bg-signal" /> Encrypted
        </span>
        <NotificationBell />
      </div>

      <nav className="flex gap-1 px-2 pb-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            className={`relative flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors
              ${tab === t.key ? 'bg-surface-hi text-paper' : 'text-muted hover:text-paper'}`}
          >
            {t.label}
            {t.key === 'chats' && chatsBadge > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-signal px-1 text-[0.62rem] font-semibold text-ink">
                {chatsBadge > 99 ? '99+' : chatsBadge}
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="min-h-0 flex-1 border-t border-line">{children}</div>

      <div className="relative border-t border-line p-2">
        <button
          onClick={() => setMenuOpen((o) => !o)}
          className="flex w-full items-center gap-2.5 rounded-xl p-2 text-left hover:bg-surface-alt"
        >
          <Avatar name={user?.full_name || user?.username || '?'} status="online" size={34} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-paper">{user?.full_name || user?.username}</span>
            <span className="block truncate text-xs text-muted">@{user?.username}</span>
          </span>
        </button>

        {menuOpen && (
          <div className="absolute bottom-[3.4rem] left-2 right-2 overflow-hidden rounded-xl border border-line bg-surface-hi shadow-xl">
            <button
              onClick={() => {
                onOpenProfile()
                setMenuOpen(false)
              }}
              className="block w-full px-3.5 py-2.5 text-left text-sm text-paper hover:bg-surface-alt"
            >
              View profile
            </button>
            {user?.is_admin && (
              <button
                onClick={() => {
                  navigate('/admin')
                  setMenuOpen(false)
                }}
                className="block w-full px-3.5 py-2.5 text-left text-sm text-paper hover:bg-surface-alt"
              >
                Admin dashboard
              </button>
            )}
            <button
              onClick={toggle}
              className="flex w-full items-center justify-between px-3.5 py-2.5 text-left text-sm text-paper hover:bg-surface-alt"
            >
              <span>{theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}</span>
              <span className="text-xs text-muted">{theme === 'dark' ? '🌙' : '☀️'}</span>
            </button>
            <button
              onClick={() => {
                lock()
                setMenuOpen(false)
              }}
              className="block w-full px-3.5 py-2.5 text-left text-sm text-paper hover:bg-surface-alt"
            >
              Lock session
            </button>
            <button
              onClick={logout}
              className="block w-full px-3.5 py-2.5 text-left text-sm text-danger hover:bg-danger-dim"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
