import { createPortal } from 'react-dom'
import { useCall } from '../../context/CallContext.jsx'
import Avatar from '../common/Avatar.jsx'

export default function IncomingCallModal() {
  const { callState, peerUser, callType, acceptCall, rejectCall } = useCall()

  if (callState !== 'ringing') return null

  return createPortal(
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-ink/95 backdrop-blur-sm">
      <div className="relative">
        <span className="absolute inset-0 -m-3 animate-ping rounded-full bg-signal/20" />
        <Avatar name={peerUser?.full_name || peerUser?.username || '?'} src={peerUser?.profile_picture} size={96} />
      </div>

      <p className="mt-6 font-display text-2xl font-semibold text-paper">
        {peerUser?.full_name || peerUser?.username}
      </p>
      <p className="mt-1 text-sm text-muted">Incoming {callType === 'video' ? 'video' : 'voice'} call…</p>

      <div className="mt-10 flex items-center gap-8">
        <button
          onClick={rejectCall}
          aria-label="Decline call"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-danger text-paper shadow-lg transition-transform hover:scale-105"
        >
          <PhoneOffIcon />
        </button>
        <button
          onClick={acceptCall}
          aria-label="Accept call"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-signal text-ink shadow-lg transition-transform hover:scale-105"
        >
          {callType === 'video' ? <VideoIcon /> : <PhoneIcon />}
        </button>
      </div>
    </div>,
    document.body,
  )
}

function PhoneIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.4.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.5 21 3 13.5 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1L6.6 10.8Z" />
    </svg>
  )
}

function PhoneOffIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m2 2 20 20M10.5 5.5c1 0 2 .2 2.9.5.4.1.5.5.4.9l-.7 2.4c-.1.4 0 .8.3 1l1.2 1.1M17 14l1.4 1.3c.3.2.7.3 1 .2 1.1-.4 2.3-.6 3.6-.6.5 0 1 .4 1 1v3c0 .5-.5 1-1 1a17 17 0 0 1-8.6-2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function VideoIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
      <path d="M17 10.5V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3.5l4 3.2a1 1 0 0 0 1.6-.8V8.1a1 1 0 0 0-1.6-.8l-4 3.2Z" />
    </svg>
  )
}
