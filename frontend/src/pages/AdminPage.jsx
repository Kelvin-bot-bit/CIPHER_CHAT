import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSocket } from '../context/SocketContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import AdminOverview from '../components/admin/AdminOverview.jsx'
import AdminMonitoring from '../components/admin/AdminMonitoring.jsx'
import AdminAlerts from '../components/admin/AdminAlerts.jsx'
import AdminLogs from '../components/admin/AdminLogs.jsx'
import AdminUsers from '../components/admin/AdminUsers.jsx'
import AdminAuditLogs from '../components/admin/AdminAuditLogs.jsx'
import AdminSystemStatus from '../components/admin/AdminSystemStatus.jsx'
import { usePoll } from '../components/admin/adminUi.jsx'

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'monitoring', label: 'Monitoring' },
  { key: 'alerts', label: 'Alerts' },
  { key: 'logs', label: 'Logs' },
  { key: 'users', label: 'Users' },
  { key: 'audit', label: 'Audit logs' },
  { key: 'system', label: 'System' },
]

export default function AdminPage() {
  const [tab, setTab] = useState('overview')
  const [alertTick, setAlertTick] = useState(0)
  const { socket } = useSocket()
  const toast = useToast()

  // Cheap poll that drives the badge on the Alerts tab.
  const summary = usePoll('/admin/monitoring/alerts/summary', { _t: alertTick }, 20000)
  const active = summary.data?.total_active || 0
  const critical = summary.data?.critical || 0

  // New alerts are pushed over the existing socket the moment they are raised.
  const onAlert = useCallback(
    (alert) => {
      setAlertTick((n) => n + 1)
      const msg = `${alert.title}${alert.message ? `: ${alert.message}` : ''}`.slice(0, 160)
      if (alert.severity === 'critical') toast.error(msg)
      else toast.info(msg)
    },
    [toast],
  )
  useEffect(() => {
    if (!socket) return undefined
    socket.on('admin_alert', onAlert)
    return () => socket.off('admin_alert', onAlert)
  }, [socket, onAlert])

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-ink">
      <header className="flex items-center gap-4 border-b border-line px-4 py-3 sm:px-6">
        <Link to="/" className="text-muted hover:text-paper" aria-label="Back to chat">
          <BackIcon />
        </Link>
        <div>
          <p className="font-display text-lg font-semibold text-paper">Admin</p>
          <p className="text-xs text-muted">Users, activity, monitoring, and system health</p>
        </div>
      </header>

      <nav className="flex gap-1 overflow-x-auto border-b border-line px-4 py-2 sm:px-6" aria-label="Admin sections">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            aria-current={tab === t.key ? 'page' : undefined}
            className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors
              ${tab === t.key ? 'bg-surface-hi text-paper' : 'text-muted hover:text-paper'}`}
          >
            {t.label}
            {t.key === 'alerts' && active > 0 && (
              <span
                className={`inline-flex min-w-[1.25rem] items-center justify-center rounded-full px-1.5 text-[11px] font-semibold ${
                  critical > 0 ? 'bg-danger text-white' : 'bg-amber text-ink'
                }`}
              >
                {active}
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {tab === 'overview' && <AdminOverview />}
        {tab === 'monitoring' && (
          <AdminMonitoring
            onOpenAlerts={() => setTab('alerts')}
            onOpenLogs={() => setTab('logs')}
            onOpenAudit={() => setTab('audit')}
          />
        )}
        {tab === 'alerts' && <AdminAlerts refreshKey={alertTick} onChanged={() => setAlertTick((n) => n + 1)} />}
        {tab === 'logs' && <AdminLogs />}
        {tab === 'users' && <AdminUsers />}
        {tab === 'audit' && <AdminAuditLogs />}
        {tab === 'system' && <AdminSystemStatus />}
      </div>
    </div>
  )
}

function BackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
