import { useState } from 'react'
import { useToast } from '../../context/ToastContext.jsx'
import {
  Button,
  Card,
  CopyChip,
  Empty,
  JsonBlock,
  Loading,
  Pager,
  Pill,
  Segmented,
  downloadFile,
  fmtDateTime,
  fmtMs,
  fmtTimeShort,
  inputCls,
  latencyClass,
  levelTone,
  statusCodeTone,
  usePoll,
} from './adminUi.jsx'

const VIEWS = [
  { value: 'logs', label: 'Application logs' },
  { value: 'requests', label: 'HTTP requests' },
  { value: 'queries', label: 'Slow queries' },
  { value: 'events', label: 'Event history' },
]

export default function AdminLogs() {
  const [view, setView] = useState('logs')
  const [requestId, setRequestId] = useState('')
  const [live, setLive] = useState(true)

  const trace = (id) => {
    setRequestId(id)
    setView('logs')
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={view} onChange={setView} options={VIEWS} />
        {requestId && (
          <button
            onClick={() => setRequestId('')}
            className="flex items-center gap-1.5 rounded-full bg-signal/15 px-2.5 py-1 text-xs text-signal"
            title="Clear request filter"
          >
            Following request <span className="font-mono">{requestId.slice(0, 8)}</span> ✕
          </button>
        )}
        {(view === 'logs' || view === 'requests') && (
          <label className="ml-auto flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} className="accent-signal" />
            <span className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${live ? 'animate-pulse bg-signal' : 'bg-muted'}`} />
              Live
            </span>
          </label>
        )}
      </div>

      {view === 'logs' && <AppLogs live={live} requestId={requestId} onTrace={setRequestId} />}
      {view === 'requests' && <Requests live={live} requestId={requestId} onTrace={trace} />}
      {view === 'queries' && <SlowQueries />}
      {view === 'events' && <Events requestId={requestId} onTrace={trace} />}
    </div>
  )
}

/* ------------------------------------------------------------ app logs */
function AppLogs({ live, requestId, onTrace }) {
  const toast = useToast()
  const [level, setLevel] = useState('INFO')
  const [q, setQ] = useState('')
  const [logger, setLogger] = useState('')
  const [open, setOpen] = useState(null)
  const params = { limit: 300, level, q: q || undefined, logger: logger || undefined, request_id: requestId || undefined }
  const { data, loading } = usePoll('/admin/monitoring/logs', params, live ? 3000 : 0)

  const exportLogs = async () => {
    try {
      await downloadFile('/admin/monitoring/logs/export', { level, q: q || undefined, request_id: requestId || undefined }, 'app-logs.ndjson')
    } catch {
      toast.error('Export failed')
    }
  }

  return (
    <Card>
      <div className="mb-3 flex flex-wrap gap-2">
        <select value={level} onChange={(e) => setLevel(e.target.value)} className={inputCls} aria-label="Minimum level">
          <option value="INFO">Info and above</option>
          <option value="WARNING">Warnings and errors</option>
          <option value="ERROR">Errors only</option>
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search messages and stack traces" className={`${inputCls} min-w-[14rem] flex-1`} />
        <input value={logger} onChange={(e) => setLogger(e.target.value)} placeholder="Logger (e.g. security)" className={`${inputCls} w-44`} />
        <Button onClick={exportLogs}>Export</Button>
      </div>
      {loading && !data ? (
        <Loading />
      ) : !data?.logs?.length ? (
        <Empty>No log lines match these filters.</Empty>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">
            Showing the newest {data.logs.length} of up to {data.capacity} buffered lines. Older lines are in logs/app.log and logs/error.log.
          </p>
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line font-mono text-xs">
            {data.logs.map((l) => (
              <li key={l.id}>
                <button onClick={() => setOpen(open === l.id ? null : l.id)} className="flex w-full items-start gap-2.5 px-3 py-1.5 text-left hover:bg-surface-alt">
                  <span className="w-[4.25rem] shrink-0 whitespace-nowrap text-muted">{fmtTimeShort(l.ts)}</span>
                  <Pill tone={levelTone(l.level)} className="w-[4.25rem] shrink-0 justify-center">
                    {l.level}
                  </Pill>
                  <span className="hidden w-32 shrink-0 truncate text-muted sm:block" title={l.logger}>{l.logger}</span>
                  <span className="min-w-0 flex-1 break-words text-paper">{l.message}</span>
                  {l.username && <span className="hidden shrink-0 text-muted md:block">@{l.username}</span>}
                </button>
                {open === l.id && (
                  <div className="space-y-2 bg-surface-alt px-3 pb-3 pt-1">
                    <div className="flex flex-wrap items-center gap-2 text-muted">
                      <span>{fmtDateTime(l.ts)}</span>
                      <span>
                        {l.module}.{l.function}:{l.line}
                      </span>
                      {l.request_id && (
                        <button onClick={() => onTrace(l.request_id)} className="rounded bg-surface-hi px-1.5 py-0.5 text-signal hover:underline">
                          follow request {l.request_id.slice(0, 8)}
                        </button>
                      )}
                    </div>
                    {l.fields && <JsonBlock value={l.fields} />}
                    {l.exception && <JsonBlock value={l.exception} />}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

/* ------------------------------------------------------------ requests */
function Requests({ live, requestId, onTrace }) {
  const [status, setStatus] = useState('')
  const [method, setMethod] = useState('')
  const [q, setQ] = useState('')
  const [slow, setSlow] = useState(false)
  const [open, setOpen] = useState(null)
  const params = {
    limit: 200,
    status: status || undefined,
    method: method || undefined,
    q: q || undefined,
    slow: slow ? 1 : undefined,
    request_id: requestId || undefined,
  }
  const { data, loading } = usePoll('/admin/monitoring/requests', params, live ? 3000 : 0)

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls} aria-label="Status">
          <option value="">All statuses</option>
          <option value="2xx">2xx success</option>
          <option value="3xx">3xx redirect</option>
          <option value="4xx">4xx client error</option>
          <option value="5xx">5xx server error</option>
        </select>
        <select value={method} onChange={(e) => setMethod(e.target.value)} className={inputCls} aria-label="Method">
          <option value="">Any method</option>
          {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search path, route or user" className={`${inputCls} min-w-[12rem] flex-1`} />
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={slow} onChange={(e) => setSlow(e.target.checked)} className="accent-signal" />
          Slow only
        </label>
      </div>
      {loading && !data ? (
        <Loading />
      ) : !data?.requests?.length ? (
        <Empty>No requests match these filters.</Empty>
      ) : (
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-xs">
            <thead>
              <tr className="text-left text-muted">
                <th className="px-4 pb-2 font-medium">Time</th>
                <th className="pb-2 pr-3 font-medium">Request</th>
                <th className="pb-2 pr-3 font-medium">Status</th>
                <th className="pb-2 pr-3 text-right font-medium">Time</th>
                <th className="pb-2 pr-3 text-right font-medium">DB</th>
                <th className="pb-2 pr-3 font-medium">User</th>
                <th className="pb-2 pr-4 font-medium">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line font-mono">
              {data.requests.map((r) => (
                <FragmentRow key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} onTrace={onTrace} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function FragmentRow({ r, open, onToggle, onTrace }) {
  return (
    <>
      <tr onClick={onToggle} className="cursor-pointer hover:bg-surface-alt">
        <td className="whitespace-nowrap px-4 py-1.5 text-muted">{fmtTimeShort(r.ts)}</td>
        <td className="max-w-[22rem] truncate py-1.5 pr-3 text-paper">
          <span className="mr-2 inline-block w-12 text-muted">{r.method}</span>
          {r.path}
        </td>
        <td className="py-1.5 pr-3">
          <Pill tone={statusCodeTone(r.status)}>{r.status}</Pill>
        </td>
        <td className={`whitespace-nowrap py-1.5 pr-3 text-right ${latencyClass(r.ms)}`}>{fmtMs(r.ms)}</td>
        <td className="whitespace-nowrap py-1.5 pr-3 text-right text-muted">
          {r.db_n ? `${r.db_n} · ${fmtMs(r.db_ms)}` : '—'}
        </td>
        <td className="py-1.5 pr-3 text-paper">{r.username || (r.user_id ? `#${r.user_id}` : <span className="text-muted">anon</span>)}</td>
        <td className="py-1.5 pr-4 text-muted">{r.ip || '—'}</td>
      </tr>
      {open && (
        <tr className="bg-surface-alt">
          <td colSpan={7} className="px-4 pb-3 pt-1">
            <div className="flex flex-wrap items-center gap-3 text-muted">
              <span>Route: <span className="text-paper">{r.route || '(unmatched)'}</span></span>
              {r.endpoint && <span>Handler: <span className="text-paper">{r.endpoint}</span></span>}
              <span>{r.bytes} bytes</span>
              {r.slow && <Pill tone="warn">slow</Pill>}
              {r.request_id && <CopyChip text={r.request_id} label={`id ${r.request_id.slice(0, 8)}`} />}
              {r.request_id && (
                <button onClick={() => onTrace(r.request_id)} className="text-signal hover:underline">
                  View its log lines
                </button>
              )}
            </div>
            {r.error && <p className="mt-1.5 text-danger">{r.error}</p>}
            {r.ua && <p className="mt-1.5 break-all text-muted">{r.ua}</p>}
          </td>
        </tr>
      )}
    </>
  )
}

/* -------------------------------------------------------- slow queries */
function SlowQueries() {
  const { data, loading } = usePoll('/admin/monitoring/slow-queries', {}, 10000)
  if (loading && !data) return <Loading />
  return (
    <Card title="Slow database queries" subtitle={`Statements slower than ${data?.threshold_ms} ms. Values are never recorded, only the SQL shape.`}>
      {!data?.queries?.length ? (
        <Empty>No slow queries since the server started.</Empty>
      ) : (
        <ul className="space-y-3">
          {data.queries.map((q, i) => (
            <li key={`${q.ts}-${i}`} className="rounded-lg border border-line bg-surface-alt p-3">
              <div className="mb-1.5 flex flex-wrap items-center gap-3 text-xs text-muted">
                <Pill tone={q.ms >= 2000 ? 'fail' : 'warn'}>{fmtMs(q.ms)}</Pill>
                <span>{fmtDateTime(q.ts)}</span>
                {q.request_id && <CopyChip text={q.request_id} label={`req ${q.request_id.slice(0, 8)}`} />}
              </div>
              <code className="block break-words font-mono text-xs text-paper">{q.statement}</code>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/* -------------------------------------------------------------- events */
function Events({ requestId, onTrace }) {
  const [page, setPage] = useState(1)
  const [level, setLevel] = useState('WARNING')
  const [category, setCategory] = useState('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)
  const { data, loading } = usePoll(
    '/admin/monitoring/events',
    { page, per_page: 30, level, category: category || undefined, q: q || undefined, request_id: requestId || undefined },
    15000,
  )
  return (
    <Card>
      <p className="mb-3 text-xs text-muted">
        Notable events kept in the database, so they survive restarts: server errors, slow requests, security signals and health changes.
      </p>
      <div className="mb-3 flex flex-wrap gap-2">
        <select value={level} onChange={(e) => { setLevel(e.target.value); setPage(1) }} className={inputCls} aria-label="Level">
          <option value="INFO">Everything</option>
          <option value="WARNING">Warnings and errors</option>
          <option value="ERROR">Errors only</option>
        </select>
        <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1) }} className={inputCls} aria-label="Category">
          <option value="">All categories</option>
          {['request', 'security', 'system', 'database', 'alert'].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="Search" className={`${inputCls} min-w-[12rem] flex-1`} />
      </div>
      {loading && !data ? (
        <Loading />
      ) : !data?.events?.length ? (
        <Empty>No events match these filters.</Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
          {data.events.map((e) => (
            <li key={e.id}>
              <button onClick={() => setOpen(open === e.id ? null : e.id)} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-left hover:bg-surface-alt">
                <Pill tone={levelTone(e.level)}>{e.level}</Pill>
                <Pill tone="muted">{e.category}</Pill>
                <span className="min-w-0 flex-1 break-words text-sm text-paper">{e.message || e.event}</span>
                <span className="text-xs text-muted">{fmtDateTime(e.created_at)}</span>
              </button>
              {open === e.id && (
                <div className="space-y-2 bg-surface-alt px-3 pb-3 pt-1 text-xs text-muted">
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    <span>Event: <span className="font-mono text-paper">{e.event}</span></span>
                    {e.username && <span>User: <span className="text-paper">{e.username}</span></span>}
                    {e.ip_address && <span>IP: <span className="font-mono text-paper">{e.ip_address}</span></span>}
                    {e.path && <span>Path: <span className="font-mono text-paper">{e.method} {e.path}</span></span>}
                    {e.status_code && <span>Status: <span className="text-paper">{e.status_code}</span></span>}
                    {e.duration_ms !== null && <span>Took: <span className="text-paper">{fmtMs(e.duration_ms)}</span></span>}
                    {e.request_id && (
                      <button onClick={() => onTrace(e.request_id)} className="text-signal hover:underline">
                        follow request {e.request_id.slice(0, 8)}
                      </button>
                    )}
                  </div>
                  {e.details?.traceback && <JsonBlock value={e.details.traceback} />}
                  {e.details && <JsonBlock value={{ ...e.details, traceback: undefined }} />}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3">
        <Pager page={page} pages={data?.pages} onChange={setPage} />
      </div>
    </Card>
  )
}
