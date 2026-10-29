import { useState } from 'react'
import { api } from '../../lib/api'
import {
  Button,
  Card,
  Empty,
  KeyValue,
  Loading,
  Meter,
  Pill,
  StatusDot,
  fmtBytes,
  fmtDateTime,
  fmtMs,
  fmtNum,
  fmtUptime,
  usePoll,
} from './adminUi.jsx'

const TITLES = {
  database: 'Database',
  storage: 'Storage',
  encryption: 'Encryption',
  scheduler: 'Background jobs',
  realtime: 'Realtime connections',
  process: 'Server process',
  configuration: 'Configuration',
}
const STATUS_LABEL = { ok: 'Healthy', warn: 'Warning', fail: 'Failing', unknown: 'Unknown' }
const STATUS_TONE = { ok: 'ok', warn: 'warn', fail: 'fail', unknown: 'muted' }

export default function AdminSystemStatus() {
  const [refreshing, setRefreshing] = useState(false)
  const health = usePoll('/admin/monitoring/health', {}, 15000)
  const errors = usePoll('/admin/monitoring/events', { level: 'ERROR', per_page: 8 }, 30000)

  const runNow = async () => {
    setRefreshing(true)
    try {
      await api.get('/admin/monitoring/health', { params: { refresh: 1 } })
      await health.reload()
    } finally {
      setRefreshing(false)
    }
  }

  if (health.loading && !health.data) return <Loading />
  const h = health.data
  if (!h) return <p className="text-sm text-muted">Health checks are unavailable.</p>

  const overall = { ok: 'All checks passing', degraded: 'Some checks need attention', down: 'The database is not responding' }[h.status]

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3.5">
        <StatusDot status={h.status} pulse />
        <div>
          <p className="text-sm font-semibold text-paper">{overall}</p>
          <p className="text-xs text-muted">
            Checked {fmtDateTime(h.checked_at)} in {fmtMs(h.duration_ms)} · re-checked every 15 seconds
          </p>
        </div>
        <Button onClick={runNow} disabled={refreshing} className="ml-auto">
          {refreshing ? 'Checking…' : 'Run checks now'}
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {Object.entries(h.checks)
          .sort(([a], [b]) => Object.keys(TITLES).indexOf(a) - Object.keys(TITLES).indexOf(b))
          .map(([name, c]) => (
          <Card
            key={name}
            title={TITLES[name] || name}
            action={<Pill tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status] || c.status}</Pill>}
          >
            {c.message && <p className="mb-3 rounded-lg bg-surface-alt px-3 py-2 text-sm text-amber">{c.message}</p>}
            <CheckBody name={name} c={c} />
          </Card>
        ))}
      </div>

      <Card title="Recent server errors" subtitle="Persisted, so they are still here after a restart">
        {!errors.data?.events?.length ? (
          <Empty>No errors recorded. 🎉</Empty>
        ) : (
          <ul className="divide-y divide-line">
            {errors.data.events.map((e) => (
              <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2.5 text-sm">
                <span className="min-w-0 flex-1 break-words text-paper">{e.message || e.event}</span>
                <span className="text-xs text-muted">{fmtDateTime(e.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function CheckBody({ name, c }) {
  const d = c.details || {}
  if (name === 'database') {
    return (
      <div className="space-y-3">
        <KeyValue
          rows={[
            ['Engine', `${d.engine || '—'}${d.version ? ` ${d.version}` : ''}`],
            ['Ping latency', fmtMs(c.latency_ms)],
            ['Database size', d.size_mb !== undefined ? `${d.size_mb} MB` : null],
            ['Server connections', d.server?.Threads_connected !== undefined ? `${d.server.Threads_connected} / ${d.max_connections}` : null],
            ['Running queries', d.server?.Threads_running],
            ['Slow queries (server total)', d.server?.Slow_queries !== undefined ? fmtNum(d.server.Slow_queries) : null],
          ]}
        />
        {d.pool?.capacity ? (
          <Meter value={d.pool.checked_out} max={d.pool.capacity} label={`App connection pool (${d.pool.checked_out}/${d.pool.capacity})`} />
        ) : null}
        {d.tables && !d.tables.error && (
          <div>
            <p className="mb-1.5 text-xs text-muted">Rows</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(d.tables).map(([t, n]) => (
                <span key={t} className="rounded-md bg-surface-alt px-2 py-1 text-xs">
                  <span className="text-muted">{t.replace(/_/g, ' ')}</span> <span className="font-mono text-paper">{fmtNum(n)}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }
  if (name === 'storage') {
    return (
      <div className="space-y-3">
        {d.disk_free_pct !== undefined && (
          <Meter value={100 - d.disk_free_pct} label={`Disk used (${d.disk_free_gb} GB free of ${d.disk_total_gb} GB)`} warnAt={85} failAt={95} />
        )}
        <KeyValue
          rows={[
            ['Uploads folder', d.exists === false ? 'Missing' : d.writable ? 'Writable' : 'Read-only'],
            ['Uploaded files', d.uploads ? `${fmtNum(d.uploads.files)}${d.uploads.truncated ? '+' : ''} · ${fmtBytes(d.uploads.bytes)}` : null],
            ['Path', <span key="p" className="font-mono text-xs">{d.path}</span>],
          ]}
        />
      </div>
    )
  }
  if (name === 'encryption') {
    return (
      <KeyValue
        rows={[
          ['AES-256-GCM self-test', d.aes_256_gcm],
          ['RSA key size', d.rsa_key_size ? `${d.rsa_key_size} bits` : null],
          ['PBKDF2 iterations', d.pbkdf2_iterations ? fmtNum(d.pbkdf2_iterations) : null],
          ['Self-test time', fmtMs(c.latency_ms)],
        ]}
      />
    )
  }
  if (name === 'scheduler') {
    return (
      <div className="space-y-2">
        <KeyValue rows={[['Scheduler', d.running === undefined ? '—' : d.running ? 'Running' : 'Stopped']]} />
        {(d.jobs || []).map((j) => (
          <p key={j.id} className="flex justify-between text-xs">
            <span className="font-mono text-muted">{j.id}</span>
            <span className="text-paper">next {j.next_run ? fmtDateTime(j.next_run) : '—'}</span>
          </p>
        ))}
      </div>
    )
  }
  if (name === 'realtime') {
    return (
      <KeyValue
        rows={[
          ['Open socket connections', fmtNum(d.socket_connections)],
          ['Connected users', fmtNum(d.connected_users)],
          ['Users marked online', fmtNum(d.users_marked_online)],
        ]}
      />
    )
  }
  if (name === 'process') {
    return (
      <div className="space-y-3">
        <KeyValue
          rows={[
            ['Uptime', fmtUptime(d.uptime_seconds)],
            ['Started', fmtDateTime(d.started_at)],
            ['Memory (this process)', d.rss_mb !== undefined ? `${d.rss_mb} MB` : null],
            ['CPU', d.cpu_percent !== undefined ? `${d.cpu_percent}%` : null],
            ['Threads', d.threads],
            ['Python', d.python],
            ['Load average', d.load_avg ? d.load_avg.join(' / ') : null],
          ]}
        />
        {d.system_memory_pct !== undefined && <Meter value={d.system_memory_pct} label="System memory" warnAt={75} failAt={90} />}
        {d.note && <p className="text-xs text-muted">{d.note}</p>}
      </div>
    )
  }
  if (name === 'configuration') {
    const yes = (b) => <Pill tone={b ? 'ok' : 'muted'}>{b ? 'on' : 'off'}</Pill>
    return (
      <div className="space-y-3">
        <KeyValue
          rows={[
            ['Environment', d.environment],
            ['Debug mode', <Pill key="d" tone={d.debug ? 'warn' : 'ok'}>{d.debug ? 'on' : 'off'}</Pill>],
            ['Rate limiting', yes(d.rate_limiting)],
            ['E-mail sending', yes(d.email_configured)],
            ['Push notifications', yes(d.push_configured)],
            ['Alert webhook', yes(d.alert_webhook)],
            ['Alert e-mail recipients', d.alert_emails || 'none'],
          ]}
        />
        {d.findings?.length > 0 && (
          <ul className="space-y-1 text-sm text-amber">
            {d.findings.map((f) => (
              <li key={f}>• {f}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }
  return null
}
