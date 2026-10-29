import { useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { api, extractErrorMessage } from '../../lib/api'
import { useToast } from '../../context/ToastContext.jsx'
import Spinner from '../common/Spinner.jsx'

// Mirrors the palette in tailwind.config.js — chart props need literal
// color values (SVG fill/stroke), not Tailwind class names, so these have
// to be kept in sync by hand if the design tokens ever change.
const COLOR = {
  signal: '#49D6AC',
  amber: '#E8A33D',
  danger: '#E5584F',
  muted: '#8C99A0',
  line: '#263138',
  surfaceHi: '#242F36',
  paper: '#ECEAE2',
}

const PIE_COLORS = [COLOR.signal, COLOR.amber, COLOR.danger, COLOR.muted]

export default function AdminOverview() {
  const toast = useToast()
  const [stats, setStats] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.get('/admin/statistics'), api.get('/admin/analytics', { params: { days: 14 } })])
      .then(([statsRes, analyticsRes]) => {
        setStats(statsRes.data)
        setAnalytics(analyticsRes.data)
      })
      .catch((err) => toast.error(extractErrorMessage(err, 'Could not load dashboard data')))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  if (!stats) {
    return <p className="text-sm text-muted">Statistics unavailable right now.</p>
  }

  const messagesData = (analytics?.messages_per_day || []).map((d) => ({
    ...d,
    label: formatShortDate(d.date),
  }))
  const signupsData = (analytics?.signups_per_day || []).map((d) => ({
    ...d,
    label: formatShortDate(d.date),
  }))

  const statusData = analytics
    ? [
        { name: 'Active', value: analytics.user_status_breakdown.active },
        { name: 'Suspended', value: analytics.user_status_breakdown.suspended },
        { name: 'Inactive', value: analytics.user_status_breakdown.inactive },
      ].filter((d) => d.value > 0)
    : []

  const loginData = analytics
    ? [
        { name: 'Success', value: analytics.login_success_vs_failed.success },
        { name: 'Failed', value: analytics.login_success_vs_failed.failed },
      ]
    : []

  const messageTypeData = analytics
    ? Object.entries(analytics.message_type_breakdown).map(([name, value]) => ({ name, value }))
    : []

  return (
    <div className="space-y-6">
      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <Kpi label="Total users" value={stats.users.total} />
        <Kpi label="Online now" value={stats.users.online} tone="signal" />
        <Kpi label="Suspended" value={stats.users.suspended} tone={stats.users.suspended > 0 ? 'danger' : undefined} />
        <Kpi label="Messages" value={stats.messages.total} />
        <Kpi label="Sent today" value={stats.messages.today} tone="signal" />
        <Kpi label="Active groups" value={stats.groups.total} />
        <Kpi
          label="Failed logins"
          value={stats.login.failed_attempts}
          tone={stats.login.failed_attempts > 0 ? 'danger' : undefined}
        />
      </div>

      {/* Trend charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Messages sent" subtitle="Last 14 days">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={messagesData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="messagesFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={COLOR.signal} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={COLOR.signal} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={COLOR.line} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke={COLOR.muted} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={COLOR.muted} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="count" stroke={COLOR.signal} strokeWidth={2} fill="url(#messagesFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="New signups" subtitle="Last 14 days">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={signupsData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={COLOR.line} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke={COLOR.muted} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={COLOR.muted} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: COLOR.surfaceHi }} />
              <Bar dataKey="count" fill={COLOR.amber} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Breakdown charts */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <ChartCard title="User status">
          <ResponsiveContainer width="100%" height={190}>
            <PieChart>
              <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70} paddingAngle={3}>
                {statusData.map((entry, i) => (
                  <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="none" />
                ))}
              </Pie>
              <Tooltip content={<ChartTooltip />} />
              <Legend
                verticalAlign="bottom"
                height={24}
                iconType="circle"
                iconSize={8}
                formatter={(value) => <span style={{ color: COLOR.muted, fontSize: 12 }}>{value}</span>}
              />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Message types">
          {messageTypeData.length > 0 ? (
            <ResponsiveContainer width="100%" height={190}>
              <PieChart>
                <Pie
                  data={messageTypeData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={45}
                  outerRadius={70}
                  paddingAngle={3}
                >
                  {messageTypeData.map((entry, i) => (
                    <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="none" />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend
                  verticalAlign="bottom"
                  height={24}
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => <span style={{ color: COLOR.muted, fontSize: 12 }}>{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart height={190} />
          )}
        </ChartCard>

        <ChartCard title="Login attempts">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={loginData} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={COLOR.line} strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" stroke={COLOR.muted} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="name" stroke={COLOR.muted} fontSize={12} tickLine={false} axisLine={false} width={60} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: COLOR.surfaceHi }} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {loginData.map((entry) => (
                  <Cell key={entry.name} fill={entry.name === 'Failed' ? COLOR.danger : COLOR.signal} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  )
}

function formatShortDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function Kpi({ label, value, tone }) {
  const toneClass = tone === 'signal' ? 'text-signal' : tone === 'danger' ? 'text-danger' : 'text-paper'
  return (
    <div className="rounded-xl border border-line bg-surface px-3.5 py-3">
      <p className={`font-display text-xl font-semibold ${toneClass}`}>{value ?? '—'}</p>
      <p className="mt-0.5 text-[0.7rem] text-muted">{label}</p>
    </div>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-2">
        <p className="text-sm font-medium text-paper">{title}</p>
        {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

function EmptyChart({ height }) {
  return (
    <div className="flex items-center justify-center text-xs text-muted" style={{ height }}>
      No data yet
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-lg border border-line bg-surface-hi px-3 py-2 text-xs shadow-lg">
      {label && <p className="mb-1 font-medium text-paper">{label}</p>}
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color || entry.fill }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  )
}
