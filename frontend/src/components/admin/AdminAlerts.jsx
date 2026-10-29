import { useState } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../context/ToastContext.jsx'
import {
  Button,
  Card,
  Empty,
  JsonBlock,
  Loading,
  Pager,
  Pill,
  Segmented,
  fmtDateTime,
  usePoll,
} from './adminUi.jsx'

const SEV_TONE = { critical: 'fail', warning: 'warn', info: 'info' }
const STATUS_TONE = { open: 'fail', acknowledged: 'warn', resolved: 'ok' }

export default function AdminAlerts({ refreshKey, onChanged }) {
  const toast = useToast()
  const [status, setStatus] = useState('active')
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState(null)
  const [busy, setBusy] = useState(null)
  const [showRules, setShowRules] = useState(false)

  const list = usePoll('/admin/monitoring/alerts', { status, page, per_page: 20, _k: refreshKey }, 10000)
  const rules = usePoll('/admin/monitoring/alerts/rules', {}, 0, { enabled: showRules })

  const act = async (alert, verb) => {
    setBusy(`${verb}-${alert.id}`)
    try {
      await api.post(`/admin/monitoring/alerts/${alert.id}/${verb}`)
      toast.success(verb === 'acknowledge' ? 'Alert acknowledged' : 'Alert resolved')
      await list.reload()
      onChanged?.()
    } catch {
      toast.error('Could not update the alert')
    } finally {
      setBusy(null)
    }
  }

  const sendTest = async () => {
    setBusy('test')
    try {
      const { data } = await api.post('/admin/monitoring/alerts/test')
      const ch = ['dashboard', ...(data.sent_to.webhook ? ['webhook'] : []), ...(data.sent_to.email ? ['email'] : [])]
      toast.success(`Test alert sent to: ${ch.join(', ')}`)
    } catch {
      toast.error('Could not send the test alert')
    } finally {
      setBusy(null)
    }
  }

  const summary = list.data?.summary
  const alerts = list.data?.alerts || []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          value={status}
          onChange={(v) => {
            setStatus(v)
            setPage(1)
          }}
          options={[
            { value: 'active', label: 'Active', count: summary?.total_active },
            { value: 'resolved', label: 'Resolved' },
            { value: 'all', label: 'All' },
          ]}
        />
        {summary && summary.total_active > 0 && (
          <div className="flex gap-2">
            {summary.critical > 0 && <Pill tone="fail">{summary.critical} critical</Pill>}
            {summary.warning > 0 && <Pill tone="warn">{summary.warning} warning</Pill>}
            {summary.acknowledged > 0 && <Pill tone="muted">{summary.acknowledged} acknowledged</Pill>}
          </div>
        )}
        <div className="ml-auto flex gap-2">
          <Button onClick={() => setShowRules((s) => !s)}>{showRules ? 'Hide rules' : 'Alert rules'}</Button>
          <Button onClick={sendTest} disabled={busy === 'test'}>
            Send test alert
          </Button>
        </div>
      </div>

      {showRules && <RulesPanel data={rules.data} loading={rules.loading} />}

      {list.loading && !list.data ? (
        <Loading />
      ) : alerts.length === 0 ? (
        <Card>
          <Empty>
            {status === 'active'
              ? 'No active alerts. Everything the monitors are watching looks healthy.'
              : 'No alerts to show.'}
          </Empty>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {alerts.map((a) => {
            const open = openId === a.id
            return (
              <li key={a.id} className="rounded-xl border border-line bg-surface">
                <div className="flex flex-wrap items-start gap-3 p-4">
                  <span
                    className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                      a.status === 'resolved' ? 'bg-muted' : a.severity === 'critical' ? 'bg-danger' : 'bg-amber'
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-paper">{a.title}</p>
                      <Pill tone={SEV_TONE[a.severity]}>{a.severity}</Pill>
                      <Pill tone={STATUS_TONE[a.status]}>{a.status}</Pill>
                      {a.occurrences > 1 && <Pill tone="muted">× {a.occurrences}</Pill>}
                    </div>
                    {a.message && <p className="mt-1 text-sm text-muted">{a.message}</p>}
                    <p className="mt-1.5 text-xs text-muted">
                      First seen {fmtDateTime(a.first_seen)} · last seen {fmtDateTime(a.last_seen)}
                      {a.acknowledged_by && ` · acknowledged by ${a.acknowledged_by}`}
                      {a.resolved_at && ` · resolved ${fmtDateTime(a.resolved_at)} by ${a.resolved_by}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {a.status === 'open' && (
                      <Button onClick={() => act(a, 'acknowledge')} disabled={busy === `acknowledge-${a.id}`}>
                        Acknowledge
                      </Button>
                    )}
                    {a.status !== 'resolved' && (
                      <Button onClick={() => act(a, 'resolve')} disabled={busy === `resolve-${a.id}`}>
                        Resolve
                      </Button>
                    )}
                    {a.details && (
                      <Button onClick={() => setOpenId(open ? null : a.id)}>{open ? 'Hide' : 'Details'}</Button>
                    )}
                  </div>
                </div>
                {open && a.details && (
                  <div className="border-t border-line px-4 pb-4 pt-3">
                    {a.details.traceback && (
                      <>
                        <p className="mb-1.5 text-xs font-medium text-muted">Stack trace</p>
                        <JsonBlock value={a.details.traceback} className="mb-3" />
                      </>
                    )}
                    <p className="mb-1.5 text-xs font-medium text-muted">Context</p>
                    <JsonBlock value={{ ...a.details, traceback: undefined }} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <Pager page={page} pages={list.data?.pages} onChange={setPage} />
    </div>
  )
}

function RulesPanel({ data, loading }) {
  if (loading && !data) return <Loading />
  if (!data) return null
  const ch = data.channels
  return (
    <Card
      title="What is being watched"
      subtitle={`Rules are evaluated every ${data.evaluation_interval_seconds} seconds. Conditions clear automatically after two clean checks.`}
    >
      <div className="mb-4 flex flex-wrap gap-2 text-xs">
        <Pill tone="ok">Dashboard: on</Pill>
        <Pill tone={ch.webhook ? 'ok' : 'muted'}>Webhook: {ch.webhook ? 'configured' : 'not set (ALERT_WEBHOOK_URL)'}</Pill>
        <Pill tone={ch.email ? 'ok' : 'muted'}>
          E-mail: {ch.email ? `from ${ch.email_min_severity}` : 'not set (ALERT_EMAILS + mail settings)'}
        </Pill>
        <Pill tone="muted">Re-notify every {Math.round(ch.cooldown_seconds / 60)} min</Pill>
      </div>
      <ul className="divide-y divide-line">
        {data.rules.map((r) => (
          <li key={r.rule} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${r.firing ? 'bg-danger' : 'bg-signal'}`} />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-paper">
                {r.title} <span className="text-xs text-muted">· {r.severity}</span>
              </p>
              <p className="text-xs text-muted">{r.description}</p>
            </div>
            <Pill tone={r.firing ? 'fail' : 'ok'}>{r.firing ? 'Firing' : 'OK'}</Pill>
          </li>
        ))}
      </ul>
    </Card>
  )
}
