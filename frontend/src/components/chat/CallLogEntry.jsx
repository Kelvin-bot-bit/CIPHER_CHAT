import { formatClock } from '../../utils/time'
import { formatDuration } from '../../utils/callLog'

// A finished call, shown as a centered pill in the conversation timeline.
// What it says depends on who is looking:
//   completed            -> "Outgoing/Incoming voice call · 2:35"
//   missed (you called)  -> "Outgoing voice call · No answer"
//   missed (they called) -> "Missed voice call"            (red)
//   declined             -> "Outgoing voice call · Declined" / "Declined voice call"
export default function CallLogEntry({ call, viewerId, createdAt }) {
  const outgoing = call.caller_id === viewerId
  const isVideo = call.call_type === 'video'
  const noun = isVideo ? 'video call' : 'voice call'
  const direction = outgoing ? 'Outgoing' : 'Incoming'

  let label = `${direction} ${noun}`
  let detail = null
  let tone = 'ok'

  if (call.status === 'completed') {
    detail = formatDuration(call.duration_seconds)
  } else if (call.status === 'missed') {
    if (outgoing) {
      detail = 'No answer'
      tone = 'muted'
    } else {
      label = `Missed ${noun}`
      tone = 'bad'
    }
  } else if (call.status === 'declined') {
    if (outgoing) {
      detail = 'Declined'
    } else {
      label = `Declined ${noun}`
    }
    tone = 'muted'
  }

  const iconStyle = {
    ok: 'bg-signal-dim text-signal',
    muted: 'bg-surface-hi text-muted',
    bad: 'bg-danger-dim text-danger',
  }[tone]

  return (
    <div className="flex justify-center py-1">
      <div className="flex max-w-full flex-wrap items-center justify-center gap-x-2.5 gap-y-1 rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs">
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${iconStyle}`}>
          {isVideo ? <VideoIcon /> : <PhoneIcon />}
        </span>
        <span className={`font-medium ${tone === 'bad' ? 'text-danger' : 'text-paper'}`}>{label}</span>
        {detail && <span className="text-muted">· {detail}</span>}
        <span className="text-muted">{formatClock(createdAt)}</span>
      </div>
    </div>
  )
}

export function PhoneIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.4.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.5 21 3 13.5 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1L6.6 10.8Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function VideoIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="m16 10 5.2-3.1a1 1 0 0 1 1.5.9v8.4a1 1 0 0 1-1.5.9L16 14" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
