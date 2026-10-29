import { formatClock } from '../../utils/time'
import { formatDuration } from '../../utils/callLog'
import { PhoneIcon, VideoIcon } from './CallLogEntry.jsx'

// A finished group call, shown as a centered pill like a 1:1 call. What it
// says depends on whether the viewer was actually in it:
//   joined, others too  -> "Group video call · 12:34 · 3 people"
//   joined, nobody else -> "Group voice call · No one joined"
//   never joined        -> "Missed group video call · started by Alex"  (red)
export default function GroupCallLogEntry({ call, viewerId, createdAt, starterName }) {
  const isVideo = call.call_type === 'video'
  const noun = isVideo ? 'video call' : 'voice call'
  const peopleCount = call.participant_ids.length
  const joined = call.participant_ids.includes(viewerId)

  let label = `Group ${noun}`
  let detail = null
  let tone = 'ok'

  if (!joined) {
    label = `Missed group ${noun}`
    detail = starterName ? `started by ${starterName}` : null
    tone = 'bad'
  } else if (peopleCount <= 1) {
    detail = 'No one joined'
    tone = 'muted'
  } else {
    detail = `${formatDuration(call.duration_seconds)} · ${peopleCount} people`
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
