import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useToast } from '../../context/ToastContext.jsx'
import {
  Button,
  COLOR,
  Card,
  CopyChip,
  Empty,
  JsonBlock,
  Kpi,
  Loading,
  Pager,
  Pill,
  Segmented,
  UserCell,
  downloadFile,
  fmtDateTime,
  fmtNum,
  humanizeAction,
  inputCls,
  usePoll,
} from './adminUi.jsx'

export default function AdminAuditLogs() {
  const [view, setView] = useState('activity')
  return (
    <div className="space-y-4">
      <Segmented
        value={view}
        onChange={setView}
        options={[
          { value: 'activity', label: 'Activity' },
          { value: 'logins', label: 'Login attempts' },
        ]}
      />
      {view === 'activity' ? <Activity onShowLogins={() => setView('logins')} /> : <LoginAttempts />}
    </div>
  )
}

/* ------------------------------------------------------------ activity */
function Activity({ onShowLogins }) {
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [action, setAction] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [open, setOpen] = useState(null)

  const filters = {
    q: q || undefined,
    action: action || undefined,
    status: status || undefined,
    from: from ? `${from}T00:00:00` : undefined,
    to: to ? `${to}T23:59:59` : undefined,
  }
  const list = usePoll('/admin/audit-logs', { page, per_page: 30, ...filters }, 15000)
  const actions = usePoll('/admin/audit-logs/actions', {}, 0)

  const reset = (setter) => (e) => {
    setter(e.target.value)
    setPage(1)
  }

  const exportCsv = async () => {
    try {
      await downloadFile('/admin/audit-logs/export', filters, 'audit-logs.csv')
      toast.success('Audit log exported')
    } catch {
      toast.error('Export failed')
    }
  }

  const logs = list.data?.logs || []

  return (
    <Card>
      <div className="mb-3 flex flex-wrap gap-2">
        <input
          value={q}
          onChange={reset(setQ)}
          placeholder="Search name, e-mail, IP address or action"
          className={`${inputCls} min-w-[14rem] flex-1`}
        />
        <select value={action} onChange={reset(setAction)} className={inputCls} aria-label="Action">
          <option value="">All actions</option>
          {(actions.data?.actions || []).map((a) => (
            <option key={a.action} value={a.action}>
              {humanizeAction(a.action)} ({a.count})
            </option>
          ))}
        </select>
        <select value={status} onChange={reset(setStatus)} className={inputCls} aria-label="Outcome">
          <option value="">Any outcome</option>
          <option value="success">Succeeded</option>
          <option value="failure">Failed</option>
        </select>
        <input type="date" value={from} onChange={reset(setFrom)} className={inputCls} aria-label="From date" />
        <input type="date" value={to} onChange={reset(setTo)} className={inputCls} aria-label="To date" />
        <Button onClick={exportCsv}>Export CSV</Button>
      </div>

      {list.loading && !list.data ? (
        <Loading />
      ) : logs.length === 0 ? (
        <Empty>No audit entries match these filters.</Empty>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">
            {fmtNum(list.data.total)} entr{list.data.total === 1 ? 'y' : 'ies'}
            {status === '' && (
              <>
                {' '}
                · login problems also have their own view under{' '}
                <button onClick={onShowLogins} className="text-signal hover:underline">
                  Login attempts
                </button>
              </>
            )}
          </p>
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
            {logs.map((log) => (
              <AuditRow key={log.id} log={log} open={open === log.id} onToggle={() => setOpen(open === log.id ? null : log.id)} />
            ))}
          </ul>
          <div className="mt-3">
            <Pager page={page} pages={list.data.pages} onChange={setPage} />
          </div>
        </>
      )}
    </Card>
  )
}

function reasonOf(log) {
  return log.status === 'failure' && log.details && typeof log.details === 'object'
    ? log.details.reason || log.details.error || null
    : null
}

function AuditRow({ log, open, onToggle }) {
  const reason = reasonOf(log)
  const changes = log.details?.changes
  const failed = log.status === 'failure'
  return (
    <li>
      <button onClick={onToggle} className="grid w-full gap-x-4 gap-y-2 px-3 py-3 text-left hover:bg-surface-alt md:grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)_auto]">
        <UserCell user={log.user} fallbackId={log.user_id} />
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm text-paper">
            <span className={`h-2 w-2 shrink-0 rounded-full ${failed ? 'bg-danger' : 'bg-signal'}`} />
            <span className="font-medium">{humanizeAction(log.action)}</span>
            {failed && !log.action.endsWith('_failed') && <Pill tone="fail">Failed</Pill>}
            {log.target && log.target.id !== log.user?.id && (
              <span className="text-muted">
                on <span className="text-paper">{log.target.username || `#${log.target.id}`}</span>
                {log.target.deleted && ' (deleted)'}
              </span>
            )}
          </p>
          {reason && <p className="mt-1 text-sm text-danger">Reason: {reason}</p>}
          {changes && Object.keys(changes).length > 0 && (
            <p className="mt-1 text-xs text-muted">
              {Object.entries(changes)
                .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${String(v.from)} → ${String(v.to)}`)
                .join(' · ')}
            </p>
          )}
          <p className="mt-1 text-xs text-muted">
            {[log.ip_address, log.device].filter(Boolean).join(' · ')}
          </p>
        </div>
        <p className="whitespace-nowrap text-xs text-muted md:text-right">{fmtDateTime(log.created_at)}</p>
      </button>
      {open && (
        <div className="space-y-2 bg-surface-alt px-3 pb-3 pt-1 text-xs text-muted">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span>Action code: <span className="font-mono text-paper">{log.action}</span></span>
            {log.resource_type && (
              <span>
                Resource: <span className="text-paper">{log.resource_type}{log.resource_id ? ` #${log.resource_id}` : ''}</span>
              </span>
            )}
            {log.request_id && <CopyChip text={log.request_id} label={`request ${log.request_id.slice(0, 8)}`} />}
          </div>
          {log.user_agent && <p className="break-all">{log.user_agent}</p>}
          {log.details && <JsonBlock value={log.details} />}
        </div>
      )}
    </li>
  )
}

/* ------------------------------------------------------ login attempts */
function LoginAttempts() {
  const [hours, setHours] = useState(24)
  const [page, setPage] = useState(1)
  const [outcome, setOutcome] = useState('failed')
  const [code, setCode] = useState('')
  const [q, setQ] = useState('')
  const [ip, setIp] = useState('')
  const [open, setOpen] = useState(null)

  const summary = usePoll('/admin/login-attempts/summary', { hours }, 20000)
  const list = usePoll(
    '/admin/login-attempts',
    { page, per_page: 25, outcome: outcome || undefined, failure_code: code || undefined, q: q || undefined, ip: ip || undefined },
    15000,
  )
  const s = summary.data
  const attempts = list.data?.attempts || []

  const focus = (patch) => {
    if ('code' in patch) setCode(patch.code)
    if ('ip' in patch) setIp(patch.ip)
    if ('q' in patch) setQ(patch.q)
    setOutcome('failed')
    setPage(1)
  }

  return (
    <div className="space-y-4">
      {s && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted">Sign-in activity, last {hours === 24 ? '24 hours' : `${hours / 24} days`}</p>
            <Segmented
              size="sm"
              value={hours}
              onChange={setHours}
              options={[
                { value: 24, label: '24 h' },
                { value: 72, label: '3 days' },
                { value: 168, label: '7 days' },
              ]}
            />
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Kpi label="Successful" value={fmtNum(s.success)} tone="ok" />
            <Kpi label="Failed" value={fmtNum(s.failed)} tone={s.failed ? 'warn' : undefined}
                 sub={s.total ? `${((s.failed / s.total) * 100).toFixed(0)}% of attempts` : undefined} />
            <Kpi label="Locked accounts" value={s.locked_accounts.length} tone={s.locked_accounts.length ? 'fail' : undefined} sub="right now" />
            <Kpi label="Distinct IPs failing" value={s.top_ips.length} sub="top 10 listed below" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Why logins failed" subtitle="Click a reason to filter the list">
              {s.by_reason.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted">No failed logins in this period.</p>
              ) : (
                <ul className="space-y-2.5">
                  {s.by_reason.map((r) => (
                    <li key={r.code}>
                      <button onClick={() => focus({ code: r.code })} className="w-full text-left">
                        <div className="mb-1 flex justify-between text-sm">
                          <span className="text-paper">{r.label}</span>
                          <span className="font-mono text-xs text-muted">{r.count}</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-surface-hi">
                          <div className="h-full rounded-full bg-danger/80" style={{ width: `${(r.count / s.failed) * 100}%` }} />
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Attempts over time">
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={s.trend.map((t) => ({ ...t, label: new Date(t.t).toLocaleString([], hours > 24 ? { weekday: 'short', hour: '2-digit' } : { hour: '2-digit' }) }))} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                    <CartesianGrid stroke={COLOR.line} vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: COLOR.muted, fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={24} />
                    <YAxis tick={{ fill: COLOR.muted, fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
                    <Tooltip cursor={{ fill: COLOR.surfaceHi, opacity: 0.4 }} contentStyle={{ background: COLOR.surfaceHi, border: `1px solid ${COLOR.line}`, borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="success" name="Successful" stackId="a" fill={COLOR.signal} />
                    <Bar dataKey="failed" name="Failed" stackId="a" fill={COLOR.danger} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Noisiest IP addresses">
              {s.top_ips.length === 0 ? (
                <p className="py-3 text-center text-sm text-muted">None</p>
              ) : (
                <ul className="space-y-2">
                  {s.top_ips.slice(0, 6).map((r) => (
                    <li key={r.ip}>
                      <button onClick={() => focus({ ip: r.ip })} className="flex w-full items-center justify-between gap-2 text-left text-sm hover:text-signal">
                        <span className="font-mono text-xs text-paper">{r.ip}</span>
                        <span className="text-xs text-muted">
                          {r.failed} failed{r.distinct_accounts > 1 ? ` · ${r.distinct_accounts} accounts` : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Most targeted accounts">
              {s.top_accounts.length === 0 ? (
                <p className="py-3 text-center text-sm text-muted">None</p>
              ) : (
                <ul className="space-y-2">
                  {s.top_accounts.slice(0, 6).map((r) => (
                    <li key={r.identifier}>
                      <button onClick={() => focus({ q: r.identifier })} className="flex w-full items-center justify-between gap-2 text-left text-sm hover:text-signal">
                        <span className="flex min-w-0 items-center gap-2 truncate text-paper">
                          {r.identifier}
                          {!r.exists && <Pill tone="fail">no such account</Pill>}
                        </span>
                        <span className="shrink-0 text-xs text-muted">{r.failed} failed</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Locked right now">
              {s.locked_accounts.length === 0 ? (
                <p className="py-3 text-center text-sm text-muted">No accounts are locked.</p>
              ) : (
                <ul className="space-y-2">
                  {s.locked_accounts.map((r) => (
                    <li key={r.identifier} className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate text-paper">{r.identifier}</span>
                      <Pill tone="fail">{r.failed} failures</Pill>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}

      <Card title="All login attempts">
        <div className="mb-3 flex flex-wrap gap-2">
          <select value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1) }} className={inputCls} aria-label="Outcome">
            <option value="failed">Failed only</option>
            <option value="success">Successful only</option>
            <option value="">All attempts</option>
          </select>
          <select value={code} onChange={(e) => { setCode(e.target.value); setPage(1) }} className={inputCls} aria-label="Reason">
            <option value="">Any reason</option>
            {Object.entries(list.data?.reasons || {}).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="Username, name, e-mail or IP" className={`${inputCls} min-w-[12rem] flex-1`} />
          {(ip || code || q) && (
            <Button onClick={() => { setIp(''); setCode(''); setQ(''); setPage(1) }}>
              Clear filters{ip ? ` (${ip})` : ''}
            </Button>
          )}
        </div>

        {list.loading && !list.data ? (
          <Loading />
        ) : attempts.length === 0 ? (
          <Empty>No login attempts match these filters.</Empty>
        ) : (
          <>
            <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
              {attempts.map((a) => (
                <li key={a.id}>
                  <button onClick={() => setOpen(open === a.id ? null : a.id)} className="grid w-full gap-x-4 gap-y-2 px-3 py-3 text-left hover:bg-surface-alt md:grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)_auto]">
                    <UserCell
                      user={a.user || (a.identifier ? { username: a.identifier, unregistered: !a.user_id, deleted: false } : null)}
                      fallbackId={a.user_id}
                    />
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 text-sm">
                        <Pill tone={a.success ? 'ok' : 'fail'}>{a.success ? 'Signed in' : 'Failed'}</Pill>
                        {!a.success && <span className="text-danger">{a.failure_reason || 'Unknown reason'}</span>}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        {[a.ip_address, a.device].filter(Boolean).join(' · ')}
                        {!a.success && a.identifier && a.user && a.identifier.toLowerCase() !== a.user.username ? ` · typed "${a.identifier}"` : ''}
                      </p>
                    </div>
                    <p className="whitespace-nowrap text-xs text-muted md:text-right">{fmtDateTime(a.login_time)}</p>
                  </button>
                  {open === a.id && (
                    <div className="space-y-1.5 bg-surface-alt px-3 pb-3 pt-1 text-xs text-muted">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                        {a.failure_code && <span>Reason code: <span className="font-mono text-paper">{a.failure_code}</span></span>}
                        <span>Typed: <span className="font-mono text-paper">{a.identifier || '—'}</span></span>
                        <span>Device type: <span className="text-paper">{a.device_type}</span></span>
                        {a.request_id && <CopyChip text={a.request_id} label={`request ${a.request_id.slice(0, 8)}`} />}
                      </div>
                      {a.user_agent && <p className="break-all">{a.user_agent}</p>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-3">
              <Pager page={page} pages={list.data.pages} onChange={setPage} />
            </div>
          </>
        )}
      </Card>
    </div>
  )
}
