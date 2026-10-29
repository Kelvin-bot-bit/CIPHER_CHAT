import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import Spinner from '../common/Spinner.jsx'

// Literal colours for SVG/chart props (mirrors tailwind.config.js).
export const COLOR = {
  signal: '#49D6AC',
  amber: '#E8A33D',
  danger: '#E5584F',
  muted: '#8C99A0',
  line: '#263138',
  surfaceHi: '#242F36',
  paper: '#ECEAE2',
  blue: '#5AA9E6',
}

/* ------------------------------------------------------------------ hooks */

/**
 * Fetches `url` immediately and then every `intervalMs` (0 = once). Keeps the
 * previous data on screen while refreshing so live views don't flicker, and
 * pauses while the browser tab is hidden.
 */
export function usePoll(url, params, intervalMs = 0, { enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const paramsKey = JSON.stringify(params || {})
  const alive = useRef(true)

  const load = useCallback(async () => {
    try {
      const res = await api.get(url, { params: JSON.parse(paramsKey) })
      if (!alive.current) return
      setData(res.data)
      setError(null)
    } catch (err) {
      if (alive.current) setError(err)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [url, paramsKey])

  useEffect(() => {
    alive.current = true
    if (!enabled) return undefined
    setLoading(true)
    load()
    let timer
    if (intervalMs > 0) {
      timer = setInterval(() => {
        if (!document.hidden) load()
      }, intervalMs)
    }
    return () => {
      alive.current = false
      clearInterval(timer)
    }
  }, [load, intervalMs, enabled])

  return { data, error, loading, reload: load }
}

/* ---------------------------------------------------------------- format */

export function fmtMs(v) {
  if (v === null || v === undefined) return '—'
  if (v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)} s`
  return `${v >= 100 ? Math.round(v) : Number(v).toFixed(v >= 10 ? 0 : 1)} ms`
}

export function fmtNum(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString()
}

export function fmtBytes(b) {
  if (b === null || b === undefined) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let n = b
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`
}

export function fmtUptime(sec) {
  if (sec === null || sec === undefined) return '—'
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (d) return `${d}d ${h}h`
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${sec % 60}s`
  return `${sec}s`
}

function toDate(iso) {
  if (!iso) return new Date(NaN)
  return new Date(/Z$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`)
}

export function fmtDateTime(iso) {
  if (!iso) return '—'
  const d = toDate(iso)
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, ${d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })}`
}

export function fmtTimeShort(iso) {
  if (!iso) return ''
  return toDate(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function fmtClockMinute(iso) {
  if (!iso) return ''
  return toDate(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function humanizeAction(action) {
  if (!action) return ''
  const map = {
    login: 'Signed in',
    login_failed: 'Failed login',
    logout: 'Signed out',
    register: 'Registered',
    register_failed: 'Failed registration',
    admin_update_user: 'Admin updated a user',
    admin_delete_user: 'Admin deleted a user',
    admin_export_audit_logs: 'Admin exported audit logs',
    admin_acknowledge_alert: 'Admin acknowledged an alert',
    admin_resolve_alert: 'Admin resolved an alert',
  }
  if (map[action]) return map[action]
  const clean = action.replace(/^admin_/, 'Admin: ').replace(/[._]/g, ' ')
  return clean.charAt(0).toUpperCase() + clean.slice(1)
}

/* ------------------------------------------------------------------ tones */

const TONES = {
  ok: 'bg-signal/15 text-signal',
  good: 'bg-signal/15 text-signal',
  warn: 'bg-amber/15 text-amber',
  warning: 'bg-amber/15 text-amber',
  fail: 'bg-danger/15 text-danger',
  critical: 'bg-danger/15 text-danger',
  danger: 'bg-danger/15 text-danger',
  info: 'bg-blue-400/15 text-blue-300',
  muted: 'bg-surface-hi text-muted',
}

export function Pill({ tone = 'muted', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${
        TONES[tone] || TONES.muted
      } ${className}`}
    >
      {children}
    </span>
  )
}

export function StatusDot({ status, pulse = false }) {
  const c =
    status === 'ok' || status === 'good'
      ? 'bg-signal'
      : status === 'warn' || status === 'degraded'
        ? 'bg-amber'
        : status === 'fail' || status === 'down'
          ? 'bg-danger'
          : 'bg-muted'
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      {pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-50 ${c}`} />}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${c}`} />
    </span>
  )
}

export function statusCodeTone(code) {
  if (code >= 500) return 'fail'
  if (code >= 400) return 'warn'
  if (code >= 300) return 'info'
  return 'ok'
}

export function levelTone(level) {
  if (level === 'CRITICAL' || level === 'ERROR') return 'fail'
  if (level === 'WARNING') return 'warn'
  if (level === 'DEBUG') return 'muted'
  return 'info'
}

export function latencyClass(ms) {
  if (ms === null || ms === undefined) return 'text-muted'
  if (ms >= 1000) return 'text-danger'
  if (ms >= 300) return 'text-amber'
  return 'text-paper'
}

/* ------------------------------------------------------------- primitives */

export function Card({ title, subtitle, action, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-line bg-surface ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-4 pt-3.5">
          <div>
            {title && <h3 className="text-sm font-semibold text-paper">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Kpi({ label, value, sub, tone, onClick }) {
  const color = tone === 'fail' ? 'text-danger' : tone === 'warn' ? 'text-amber' : tone === 'ok' ? 'text-signal' : 'text-paper'
  const Wrapper = onClick ? 'button' : 'div'
  return (
    <Wrapper
      onClick={onClick}
      className={`rounded-xl border border-line bg-surface px-3.5 py-3 text-left ${onClick ? 'transition-colors hover:bg-surface-alt' : ''}`}
    >
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 font-display text-2xl font-semibold leading-none ${color}`}>{value}</p>
      {sub && <p className="mt-1.5 text-xs text-muted">{sub}</p>}
    </Wrapper>
  )
}

export function Segmented({ options, value, onChange, size = 'md' }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface-alt p-0.5" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md font-medium transition-colors ${size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm'} ${
            value === o.value ? 'bg-surface-hi text-paper' : 'text-muted hover:text-paper'
          }`}
        >
          {o.label}
          {o.count !== undefined && o.count !== null && (
            <span className="ml-1.5 rounded-full bg-surface px-1.5 text-[10px] text-muted">{o.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

export const inputCls =
  'rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50 focus:outline-none'

export function Button({ children, onClick, disabled, variant = 'default', type = 'button', className = '' }) {
  const v =
    variant === 'primary'
      ? 'bg-signal text-ink hover:brightness-95'
      : variant === 'danger'
        ? 'bg-danger/15 text-danger hover:bg-danger/25'
        : 'bg-surface-hi text-paper hover:brightness-110'
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg px-3 py-2 text-sm font-medium transition disabled:opacity-50 ${v} ${className}`}
    >
      {children}
    </button>
  )
}

export function Loading() {
  return (
    <div className="flex justify-center py-12">
      <Spinner />
    </div>
  )
}

export function Empty({ children }) {
  return <p className="px-4 py-10 text-center text-sm text-muted">{children}</p>
}

export function Pager({ page, pages, onChange }) {
  if (!pages || pages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-3 text-sm">
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        className="rounded-md px-2 py-1 text-muted hover:text-paper disabled:opacity-40"
      >
        Previous
      </button>
      <span className="text-muted">
        Page {page} of {pages}
      </span>
      <button
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
        className="rounded-md px-2 py-1 text-muted hover:text-paper disabled:opacity-40"
      >
        Next
      </button>
    </div>
  )
}

export function Meter({ value, max = 100, warnAt = 70, failAt = 90, label }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const color = pct >= failAt ? 'bg-danger' : pct >= warnAt ? 'bg-amber' : 'bg-signal'
  return (
    <div>
      {label && (
        <div className="mb-1 flex justify-between text-xs text-muted">
          <span>{label}</span>
          <span className="text-paper">{pct.toFixed(0)}%</span>
        </div>
      )}
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-hi">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function KeyValue({ rows }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows
        .filter((r) => r && r[1] !== undefined && r[1] !== null && r[1] !== '')
        .map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="min-w-0 break-words text-right text-paper">{v}</dd>
          </div>
        ))}
    </dl>
  )
}

export function JsonBlock({ value, className = '' }) {
  if (value === null || value === undefined) return null
  return (
    <pre
      className={`max-h-72 overflow-auto rounded-lg border border-line bg-ink p-3 font-mono text-[11px] leading-relaxed text-muted ${className}`}
    >
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function CopyChip({ text, label }) {
  const [done, setDone] = useState(false)
  return (
    <button
      type="button"
      title="Copy"
      onClick={(e) => {
        e.stopPropagation()
        navigator.clipboard?.writeText(text)
        setDone(true)
        setTimeout(() => setDone(false), 1200)
      }}
      className="rounded bg-surface-hi px-1.5 py-0.5 font-mono text-[10px] text-muted hover:text-paper"
    >
      {done ? 'copied' : label || String(text).slice(0, 8)}
    </button>
  )
}

/**
 * Who a row is about: username, full name, e-mail and status badges.
 * Handles live accounts, deleted accounts (kept from the snapshot taken when
 * the event happened) and names that were typed but never belonged to anyone.
 */
export function UserCell({ user, fallbackId, compact = false }) {
  if (!user) {
    return (
      <div className="min-w-0">
        <p className="text-sm text-muted">{fallbackId ? `User #${fallbackId}` : 'Anonymous'}</p>
      </div>
    )
  }
  const name = user.username || (user.id ? `User #${user.id}` : 'Unknown')
  const initial = (user.full_name || user.username || '?').trim().charAt(0).toUpperCase()
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          user.unregistered ? 'bg-danger/15 text-danger' : 'bg-surface-hi text-paper'
        }`}
        aria-hidden="true"
      >
        {user.unregistered ? '?' : initial}
      </span>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-paper">
          <span className="truncate">{name}</span>
          {user.is_admin && <Pill tone="info">Admin</Pill>}
          {user.is_suspended && <Pill tone="warn">Suspended</Pill>}
          {user.is_active === false && !user.is_suspended && <Pill tone="muted">Inactive</Pill>}
          {user.deleted && <Pill tone="muted">Account deleted</Pill>}
          {user.unregistered && <Pill tone="fail">No such account</Pill>}
        </p>
        {!compact && (user.full_name || user.email) && (
          <p className="truncate text-xs text-muted">
            {[user.full_name, user.email].filter(Boolean).join(' · ')}
            {user.id ? ` · #${user.id}` : ''}
          </p>
        )}
      </div>
    </div>
  )
}

/** Downloads an authenticated endpoint as a file (the API uses cookies + CSRF, so a plain link won't do). */
export async function downloadFile(url, params, filename) {
  const res = await api.get(url, { params, responseType: 'blob' })
  const href = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(href)
}
