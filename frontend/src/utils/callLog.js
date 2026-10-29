// Helpers for showing finished 1:1 calls inside a chat's message timeline.
//
// Calls live in their own table on the server (they carry no encrypted body
// or signature, so they can't be ordinary messages), but the chat window
// keeps them in the same list as messages so ordering, scrolling and
// "stick to bottom" all just work. A call entry is tagged `kind: 'call'`
// and gets a string id so it can never collide with a numeric message id.

// Server call-log row -> timeline entry. Placed at the moment the call
// ended, which is when it appears at the bottom of the chat.
export function callToEntry(call) {
  return {
    kind: 'call',
    id: `call-${call.id}`,
    sender_id: call.caller_id,
    created_at: call.ended_at,
    call,
  }
}

// Same idea for a finished group call. Sorted at the moment it ended too.
export function groupCallToEntry(call) {
  return {
    kind: 'group_call',
    id: `group-call-${call.id}`,
    sender_id: call.started_by,
    created_at: call.ended_at,
    call,
  }
}

// Merge entries into a timeline by id (incoming wins), oldest first.
export function mergeTimeline(prev, incoming) {
  const byId = new Map(prev.map((m) => [m.id, m]))
  incoming.forEach((m) => byId.set(m.id, m))
  return Array.from(byId.values()).sort(
    (a, b) => new Date(a.created_at) - new Date(b.created_at),
  )
}

// 65 -> "1:05", 3725 -> "1:02:05"
export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}
