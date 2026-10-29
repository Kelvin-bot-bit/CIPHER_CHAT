import { useState } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts'
import {
  COLOR,
  Card,
  Kpi,
  Loading,
  Meter,
  Pill,
  Segmented,
  StatusDot,
  fmtClockMinute,
  fmtMs,
  fmtNum,
  fmtUptime,
  latencyClass,
  usePoll,
} from './adminUi.jsx'

const WINDOWS = [
  { value: 15, label: '15 min' },
  { value: 60, label: '1 hour' },
  { value: 360, label: '6 hours' },
  { value: 1440, label: '24 hours' },
]

const STATUS_COPY = {
  ok: { label: 'All systems operational', tone: 'ok' },
  degraded: { label: 'Degraded performance', tone: 'warn' },
  down: { label: 'Service disruption', tone: 'fail' },
}

export default function AdminMonitoring({ onOpenAlerts, onOpenLogs, onOpenAudit }) {
  const [minutes, setMinutes] = useState(60)
  const [sort, setSort] = useState('p95')
  const overview = usePoll('/admin/monitoring/overview', { minutes }, 5000)
  const series = usePoll('/admin/monitoring/timeseries', { minutes }, 10000)
  const endpoints = usePoll('/admin/monitoring/endpoints', { minutes, sort, limit: 12 }, 10000)

  if (overview.loading && !overview.data) return <Loading />
  const o = overview.data
  if (!o) {
    return (
      <p className="text-sm text-muted">
        Monitoring data is unavailable right now. If the server just restarted, give it a moment and refresh.
      </p>
    )
  }

  const status = STATUS_COPY[o.status] || STATUS_COPY.ok
  const live = o.live
  const points = (series.data?.points || []).map((p) => ({
    ...p,
    label: fmtClockMinute(p.t),
    ok: Math.max(0, p.requests - p.errors_5xx),
  }))
  const hasTraffic = points.some((p) => p.requests > 0)
  const errTone = live.error_rate >= 15 ? 'fail' : live.error_rate >= 5 ? 'warn' : 'ok'
  const p95Tone = (live.p95_ms || 0) >= 4000 ? 'fail' : (live.p95_ms || 0) >= 1500 ? 'warn' : undefined
  const dbTone = o.database.status === 'fail' ? 'fail' : o.database.status === 'warn' ? 'warn' : undefined
  const alertCount = o.alerts.total_active

  return (
    <div className="space-y-5">
      {/* status banner */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3.5">
        <StatusDot status={o.status} pulse />
        <div>
          <p className="text-sm font-semibold text-paper">{status.label}</p>
          <p className="text-xs text-muted">
            Up {fmtUptime(o.uptime_seconds)} · live view refreshes every 5 seconds
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {alertCount > 0 && (
            <button onClick={onOpenAlerts}>
              <Pill tone={o.alerts.critical ? 'fail' : 'warn'}>
                {alertCount} active alert{alertCount === 1 ? '' : 's'}
              </Pill>
            </button>
          )}
          <Segmented size="sm" options={WINDOWS} value={minutes} onChange={setMinutes} />
        </div>
      </div>

      {/* headline numbers (last 5 minutes unless noted) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Requests / min" value={(live.rps * 60).toFixed(live.rps * 60 >= 10 ? 0 : 1)} sub={`${fmtNum(live.requests)} in last 5 min`} />
        <Kpi
          label="Server error rate"
          value={`${live.error_rate}%`}
          tone={live.requests ? errTone : undefined}
          sub={`${live.errors_5xx} × 5xx · ${live.errors_4xx} × 4xx`}
        />
        <Kpi label="Response time p95" value={fmtMs(live.p95_ms)} tone={p95Tone} sub={`median ${fmtMs(live.p50_ms)} · p99 ${fmtMs(live.p99_ms)}`} />
        <Kpi
          label="Database"
          value={o.database.latency_ms !== null && o.database.latency_ms !== undefined ? fmtMs(o.database.latency_ms) : '—'}
          tone={dbTone}
          sub={`avg query ${fmtMs(o.database.avg_query_ms)}`}
        />
        <Kpi
          label="Active alerts"
          value={alertCount}
          tone={o.alerts.critical ? 'fail' : alertCount ? 'warn' : 'ok'}
          sub={`${o.alerts.critical} critical · ${o.alerts.warning} warning`}
          onClick={onOpenAlerts}
        />
        <Kpi
          label="Failed logins (24h)"
          value={fmtNum(o.security.failed_logins_24h)}
          tone={o.security.failed_logins_24h >= 15 ? 'warn' : undefined}
          sub={`${fmtNum(o.security.successful_logins_24h)} successful`}
          onClick={onOpenAudit}
        />
      </div>

      {/* charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Traffic and errors" subtitle={`Requests per minute, last ${WINDOWS.find((w) => w.value === minutes)?.label}`}>
          {hasTraffic ? (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={points} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gReq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={COLOR.signal} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={COLOR.signal} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={COLOR.line} vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: COLOR.muted, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={32} />
                  <YAxis tick={{ fill: COLOR.muted, fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip content={<ChartTip />} />
                  <Area type="monotone" dataKey="requests" name="Requests" stroke={COLOR.signal} fill="url(#gReq)" strokeWidth={2} />
                  <Area type="monotone" dataKey="errors_5xx" name="Server errors (5xx)" stroke={COLOR.danger} fill={COLOR.danger} fillOpacity={0.25} strokeWidth={2} />
                  <Area type="monotone" dataKey="errors_4xx" name="Client errors (4xx)" stroke={COLOR.amber} fill="none" strokeWidth={1.5} strokeDasharray="4 3" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart />
          )}
        </Card>

        <Card title="Response time" subtitle="Average and 95th percentile per minute (slow threshold: 1 s)">
          {hasTraffic ? (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={points} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                  <CartesianGrid stroke={COLOR.line} vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: COLOR.muted, fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={32} />
                  <YAxis tick={{ fill: COLOR.muted, fontSize: 11 }} tickLine={false} axisLine={false} unit=" ms" />
                  <Tooltip content={<ChartTip unit=" ms" />} />
                  <ReferenceLine y={1000} stroke={COLOR.danger} strokeDasharray="4 4" strokeOpacity={0.6} />
                  <Line type="monotone" dataKey="avg_ms" name="Average" stroke={COLOR.signal} dot={false} strokeWidth={2} connectNulls />
                  <Line type="monotone" dataKey="p95_ms" name="p95" stroke={COLOR.amber} dot={false} strokeWidth={2} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart />
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* status codes */}
        <Card title="Responses by status" subtitle={`Last ${WINDOWS.find((w) => w.value === minutes)?.label}`}>
          <StatusBreakdown codes={o.status_codes} />
        </Card>

        {/* database */}
        <Card
          title="Database health"
          action={<Pill tone={o.database.status === 'ok' ? 'ok' : o.database.status === 'warn' ? 'warn' : 'fail'}>{o.database.status === 'ok' ? 'Healthy' : o.database.status === 'warn' ? 'Degraded' : 'Down'}</Pill>}
        >
          <div className="space-y-3 text-sm">
            <Row k="Ping latency" v={fmtMs(o.database.latency_ms)} />
            <Row k="Avg query time" v={fmtMs(o.database.avg_query_ms)} />
            <Row k="Queries (window)" v={fmtNum(o.window.db_queries)} />
            <Row k="Slow queries (window)" v={fmtNum(o.window.slow_queries)} tone={o.window.slow_queries ? 'text-amber' : ''} />
            {o.database.pool?.capacity ? (
              <Meter
                value={o.database.pool.checked_out}
                max={o.database.pool.capacity}
                label={`Connection pool (${o.database.pool.checked_out}/${o.database.pool.capacity})`}
                warnAt={70}
                failAt={90}
              />
            ) : null}
          </div>
        </Card>

        {/* logs summary */}
        <Card title="Log volume" subtitle={`Last ${WINDOWS.find((w) => w.value === minutes)?.label}`} action={<button onClick={onOpenLogs} className="text-xs text-signal hover:underline">Open logs</button>}>
          <div className="space-y-2.5 text-sm">
            {['ERROR', 'WARNING', 'INFO'].map((lvl) => (
              <div key={lvl} className="flex items-center justify-between">
                <Pill tone={lvl === 'ERROR' ? 'fail' : lvl === 'WARNING' ? 'warn' : 'info'}>{lvl}</Pill>
                <span className="font-mono text-paper">{fmtNum((o.log_levels[lvl] || 0) + (lvl === 'ERROR' ? o.log_levels.CRITICAL || 0 : 0))}</span>
              </div>
            ))}
            <div className="border-t border-line pt-2.5 text-xs text-muted">
              {fmtNum(o.errors_24h)} error event{o.errors_24h === 1 ? '' : 's'} persisted in the last 24 hours
            </div>
          </div>
        </Card>
      </div>

      {/* endpoints */}
      <Card
        title="Endpoints"
        subtitle="Latency and errors per route (from the most recent requests)"
        action={
          <Segmented
            size="sm"
            value={sort}
            onChange={setSort}
            options={[
              { value: 'p95', label: 'Slowest' },
              { value: 'count', label: 'Busiest' },
              { value: 'errors', label: 'Most errors' },
            ]}
          />
        }
      >
        {endpoints.data?.endpoints?.length ? (
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="px-4 pb-2 font-medium">Route</th>
                  <th className="pb-2 pr-3 text-right font-medium">Calls</th>
                  <th className="pb-2 pr-3 text-right font-medium">Avg</th>
                  <th className="pb-2 pr-3 text-right font-medium">p95</th>
                  <th className="pb-2 pr-3 text-right font-medium">p99</th>
                  <th className="pb-2 pr-3 text-right font-medium">Max</th>
                  <th className="pb-2 pr-3 text-right font-medium">DB / call</th>
                  <th className="pb-2 pr-4 text-right font-medium">5xx</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {endpoints.data.endpoints.map((e) => (
                  <tr key={`${e.method} ${e.route}`}>
                    <td className="px-4 py-2">
                      <span className="mr-2 inline-block w-14 font-mono text-[11px] text-muted">{e.method}</span>
                      <span className="font-mono text-xs text-paper">{e.route}</span>
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-xs text-paper">{fmtNum(e.count)}</td>
                    <td className={`py-2 pr-3 text-right font-mono text-xs ${latencyClass(e.avg_ms)}`}>{fmtMs(e.avg_ms)}</td>
                    <td className={`py-2 pr-3 text-right font-mono text-xs ${latencyClass(e.p95_ms)}`}>{fmtMs(e.p95_ms)}</td>
                    <td className={`py-2 pr-3 text-right font-mono text-xs ${latencyClass(e.p99_ms)}`}>{fmtMs(e.p99_ms)}</td>
                    <td className={`py-2 pr-3 text-right font-mono text-xs ${latencyClass(e.max_ms)}`}>{fmtMs(e.max_ms)}</td>
                    <td className="py-2 pr-3 text-right font-mono text-xs text-muted">{fmtMs(e.db_avg_ms)}</td>
                    <td className={`py-2 pr-4 text-right font-mono text-xs ${e.errors_5xx ? 'text-danger' : 'text-muted'}`}>{e.errors_5xx}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-muted">No requests recorded in this window yet.</p>
        )}
      </Card>
    </div>
  )
}

function Row({ k, v, tone = '' }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted">{k}</span>
      <span className={`font-mono text-xs ${tone || 'text-paper'}`}>{v}</span>
    </div>
  )
}

function EmptyChart() {
  return <div className="flex h-56 items-center justify-center text-sm text-muted">No traffic in this window yet.</div>
}

function StatusBreakdown({ codes }) {
  const groups = { '2xx': 0, '3xx': 0, '4xx': 0, '5xx': 0 }
  Object.entries(codes || {}).forEach(([code, n]) => {
    const g = `${String(code)[0]}xx`
    if (g in groups) groups[g] += n
  })
  const total = Object.values(groups).reduce((a, b) => a + b, 0)
  if (!total) return <p className="py-6 text-center text-sm text-muted">No responses yet.</p>
  const colors = { '2xx': COLOR.signal, '3xx': COLOR.blue, '4xx': COLOR.amber, '5xx': COLOR.danger }
  return (
    <div className="space-y-3">
      {Object.entries(groups).map(([g, n]) => (
        <div key={g}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-muted">{g}</span>
            <span className="font-mono text-paper">
              {fmtNum(n)} <span className="text-muted">({((n / total) * 100).toFixed(1)}%)</span>
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-hi">
            <div className="h-full rounded-full" style={{ width: `${(n / total) * 100}%`, background: colors[g] }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function ChartTip({ active, payload, label, unit = '' }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-surface-hi px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-muted">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.stroke || p.color }}>
          {p.name}: <span className="font-mono">{p.value === null || p.value === undefined ? '—' : `${p.value}${unit}`}</span>
        </p>
      ))}
    </div>
  )
}
