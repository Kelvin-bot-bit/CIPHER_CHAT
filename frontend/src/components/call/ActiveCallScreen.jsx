import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useCall } from '../../context/CallContext.jsx'
import Avatar from '../common/Avatar.jsx'

function formatDuration(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function ActiveCallScreen() {
  const {
    callState,
    callType,
    peerUser,
    localStream,
    remoteStream,
    micEnabled,
    cameraEnabled,
    callDurationSec,
    toggleMic,
    toggleCamera,
    endCall,
  } = useCall()

  const localVideoRef = useRef(null)
  const remoteVideoRef = useRef(null)
  const remoteAudioRef = useRef(null)

  useEffect(() => {
    if (localVideoRef.current) localVideoRef.current.srcObject = localStream || null
  }, [localStream])

  useEffect(() => {
    if (callType === 'video' && remoteVideoRef.current) {
      remoteVideoRef.current.srcObject = remoteStream || null
    }
    if (callType === 'audio' && remoteAudioRef.current) {
      remoteAudioRef.current.srcObject = remoteStream || null
    }
  }, [remoteStream, callType])

  if (callState !== 'calling' && callState !== 'active') return null

  const isVideo = callType === 'video'
  const showRemoteVideo = isVideo && remoteStream

  return createPortal(
    <div className="fixed inset-0 z-[100] flex flex-col bg-ink">
      <div className="relative flex-1 overflow-hidden">
        {isVideo ? (
          <>
            {showRemoteVideo ? (
              <video ref={remoteVideoRef} autoPlay playsInline className="h-full w-full object-cover" />
            ) : (
              <CenteredPeer peerUser={peerUser} label={callState === 'calling' ? 'Ringing…' : 'Connecting…'} />
            )}

            {/* Local preview */}
            <div className="absolute bottom-24 right-4 h-32 w-24 overflow-hidden rounded-xl border border-line bg-surface shadow-lg sm:bottom-28 sm:right-6 sm:h-40 sm:w-28">
              {cameraEnabled ? (
                <video ref={localVideoRef} autoPlay playsInline muted className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-surface-hi text-muted">
                  <CameraOffIcon />
                </div>
              )}
            </div>
          </>
        ) : (
          <CenteredPeer peerUser={peerUser} label={callState === 'calling' ? 'Ringing…' : formatDuration(callDurationSec)} />
        )}

        {isVideo && (
          <div className="absolute left-0 right-0 top-0 flex items-center justify-center gap-2 pt-5">
            <span className="rounded-full bg-ink/60 px-3 py-1 text-xs text-paper backdrop-blur">
              {peerUser?.full_name || peerUser?.username}
              {callState === 'active' && ` · ${formatDuration(callDurationSec)}`}
            </span>
          </div>
        )}

        {/* Silent unless callType is audio — the video element already
            renders (and plays) the remote video+audio track together, a
            second audio element would double the sound. */}
        {callType === 'audio' && <audio ref={remoteAudioRef} autoPlay />}
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
          onClick={endCall}
          aria-label="End call"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-danger text-paper shadow-lg transition-transform hover:scale-105"
        >
          <PhoneOffIcon />
        </button>
      </div>
    </div>,
    document.body,
  )
}

function CenteredPeer({ peerUser, label }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-4">
      <Avatar name={peerUser?.full_name || peerUser?.username || '?'} src={peerUser?.profile_picture} size={112} />
      <div className="text-center">
        <p className="font-display text-2xl font-semibold text-paper">{peerUser?.full_name || peerUser?.username}</p>
        <p className="mt-1 text-sm text-muted">{label}</p>
      </div>
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
