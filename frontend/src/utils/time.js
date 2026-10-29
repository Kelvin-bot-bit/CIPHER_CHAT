// The backend serializes timestamps with Python's `datetime.utcnow().isoformat()`,
// which produces a naive string with NO timezone marker (e.g.
// "2026-08-14T07:31:00.123456", not "...123456Z"). `new Date(...)` on a
// timezone-less ISO string is treated as LOCAL time per the JS spec, even
// though the value is actually UTC — so every timestamp from the backend
// renders however-many-hours-off equal to the browser's UTC offset (e.g.
// exactly 3 hours early for EAT/UTC+3). This coerces any timezone-less
// string to explicit UTC before it's parsed, everywhere a timestamp from
// the API gets turned into a Date. The real fix is on the backend (stamp
// every serialized datetime with an explicit 'Z' or offset), but fixing
// it once here covers every timestamp in the app immediately without
// having to track down and edit every `.isoformat()` call site.
function toDate(iso) {
  if (!iso) return new Date(NaN)
  const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(iso)
  return new Date(hasTimezone ? iso : `${iso}Z`)
}

export function formatClock(iso) {
  if (!iso) return ''
  return toDate(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function formatRelative(iso) {
  if (!iso) return ''
  const then = toDate(iso).getTime()
  const now = Date.now()
  const diffSec = Math.round((now - then) / 1000)

  if (diffSec < 60) return 'just now'
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.round(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  return toDate(iso).toLocaleDateString()
}

export function formatDayDivider(iso) {
  const d = toDate(iso)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)

  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

// For disappearing messages — a rough "time left" for a future timestamp.
// Deliberately coarse (not a live-ticking second-by-second countdown):
// the actual deletion is a periodic server-side sweep anyway (see
// services/cleanup_service.py), so implying more precision than that
// would be misleading.
export function formatCountdown(iso) {
  if (!iso) return ''
  const diffSec = Math.round((toDate(iso).getTime() - Date.now()) / 1000)
  if (diffSec <= 0) return 'expiring…'
  if (diffSec < 60) return `${diffSec}s`
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h`
  const diffDay = Math.round(diffHr / 24)
  return `${diffDay}d`
}
