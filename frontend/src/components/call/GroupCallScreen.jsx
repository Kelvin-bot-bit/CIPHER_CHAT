import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useGroupCall } from '../../context/GroupCallContext.jsx'
import Avatar from '../common/Avatar.jsx'

function formatDuration(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

// Tile-count -> grid column count. Mesh calls are only practical for a
// handful of people (see the context's comment on why), so this doesn't
// need to handle dozens of tiles gracefully — just look reasonable from
// 1 up through a small group.
function columnsFor(count) {
  if (count <= 1) return 'grid-cols-1'
  if (count === 2) return 'grid-cols-1 sm:grid-cols-2'
  if (count <= 4) return 'grid-cols-2'
  return 'grid-cols-2 sm:grid-cols-3'
}

export default function GroupCallScreen() {
  const { user } = useAuth()
  const {
    callState,
    callType,
    groupInfo,
    localStream,
    participants,
    micEnabled,
    cameraEnabled,
    callDurationSec,
    toggleMic,
    toggleCamera,
    leaveGroupCall,
  } = useGroupCall()

  if (callState !== 'active') return null

  const isVideo = callType === 'video'
  const remoteEntries = Object.entries(participants)
  const tileCount = remoteEntries.length + 1 // + self

  return createPortal(
    <div className="fixed inset-0 z-[100] flex flex-col bg-ink">
      <div className="flex items-center justify-center gap-2 border-b border-line px-4 py-3">
        <span className="font-display text-sm font-semibold text-paper">{groupInfo?.name}</span>
        <span className="text-xs text-muted">
          · {tileCount} in call · {formatDuration(callDurationSec)}
        </span>
      </div>

      <div className={`grid flex-1 gap-1.5 overflow-y-auto p-1.5 ${columnsFor(tileCount)}`}>
        <SelfTile stream={localStream} isVideo={isVideo} cameraEnabled={cameraEnabled} name={user?.full_name || user?.username} />
        {remoteEntries.map(([userId, p]) => (
          <RemoteTile key={userId} participant={p} isVideo={isVideo} />
        ))}
      </div>

      <div className="flex items-center justify-center gap-6 border-t border-line bg-surface px-6 py-6">
        <button
          onClick={toggleMic}
          aria-label={micEnabled ? 'Mute microphone' : 'Unmute microphone'}
          className={`flex h-14 w-14 items-center justify-center rounded-full transition-colors
            ${micEnabled ? 'bg-surface-hi text-paper hover:brightness-110' : 'bg-danger text-paper'}`}
        >
          {micEnabled ? <MicIcon /> : <MicOffIcon />}
        </button>

        {isVideo && (
          <button
            onClick={toggleCamera}
            aria-label={cameraEnabled ? 'Turn camera off' : 'Turn camera on'}
            className={`flex h-14 w-14 items-center justify-center rounded-full transition-colors
              ${cameraEnabled ? 'bg-surface-hi text-paper hover:brightness-110' : 'bg-danger text-paper'}`}
          >
            {cameraEnabled ? <CameraIcon /> : <CameraOffIcon />}
          </button>
        )}

        <button
          onClick={leaveGroupCall}
          aria-label="Leave call"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-danger text-paper shadow-lg transition-transform hover:scale-105"
        >
          <PhoneOffIcon />
        </button>
      </div>
    </div>,
    document.body,
  )
}

function SelfTile({ stream, isVideo, cameraEnabled, name }) {
  const videoRef = useRef(null)

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream || null
  }, [stream])

  return (
    <div className="relative flex min-h-[9rem] items-center justify-center overflow-hidden rounded-xl bg-surface-hi">
      {isVideo && cameraEnabled ? (
        <video ref={videoRef} autoPlay playsInline muted className="h-full w-full object-cover" />
      ) : (
        <Avatar name={name || '?'} size={64} />
      )}
      <span className="absolute bottom-2 left-2 rounded-full bg-ink/60 px-2 py-0.5 text-[0.7rem] text-paper backdrop-blur">
        You
      </span>
    </div>
  )
}

function RemoteTile({ participant, isVideo }) {
  const { user: peerUser, stream } = participant
  const videoRef = useRef(null)
  const audioRef = useRef(null)
  const hasVideoTrack = isVideo && stream && stream.getVideoTracks().length > 0

  useEffect(() => {
    if (isVideo && videoRef.current) videoRef.current.srcObject = stream || null
    if (!isVideo && audioRef.current) audioRef.current.srcObject = stream || null
  }, [stream, isVideo])

  return (
    <div className="relative flex min-h-[9rem] items-center justify-center overflow-hidden rounded-xl bg-surface-hi">
      {hasVideoTrack ? (
        <video ref={videoRef} autoPlay playsInline className="h-full w-full object-cover" />
      ) : (
        <div className="flex flex-col items-center gap-2">
          <Avatar name={peerUser?.full_name || peerUser?.username || '?'} src={peerUser?.profile_picture} size={64} />
          {!stream && <span className="text-[0.7rem] text-muted">Connecting…</span>}
        </div>
      )}
      {!isVideo && <audio ref={audioRef} autoPlay />}
      <span className="absolute bottom-2 left-2 rounded-full bg-ink/60 px-2 py-0.5 text-[0.7rem] text-paper backdrop-blur">
        {peerUser?.full_name || peerUser?.username}
      </span>
    </div>
  )
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 19v3" strokeLinecap="round" />
    </svg>
  )
}

function MicOffIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m2 2 20 20M9 5a3 3 0 0 1 6 0v6c0 .4-.06.8-.17 1.16M15 15a3 3 0 0 1-5-2.2M5 10a7 7 0 0 0 10.6 6M19 10a7 7 0 0 1-.6 2.8M12 19v3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CameraIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="m16 10 5.2-3.1a1 1 0 0 1 1.5.9v8.4a1 1 0 0 1-1.5.9L16 14" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CameraOffIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m2 2 20 20M16 10l5.2-3.1a1 1 0 0 1 1.5.9v8.4a1 1 0 0 1-.4.8M16 16.2c-.3.3-.7.5-1.1.5H4a2 2 0 0 1-2-2V8c0-.5.2-1 .6-1.3L2 6.3" strokeLinecap="round" strokeLinejoin="round" />
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
