import { useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'

export default function VoicePlayer({ voiceNote, isOwn }) {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const [audioUrl, setAudioUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const audioRef = useRef(null)
  // Set right before we kick off a load, so the effect that watches
  // audioUrl knows whether a fresh load should autoplay once it's ready
  // (vs. just having audioUrl set without the user having asked to play,
  // which shouldn't happen here but keeps the two concerns separate).
  const autoplayRef = useRef(false)

  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    },
    [audioUrl],
  )

  // The <audio> element is always mounted (not conditionally on audioUrl)
  // so audioRef.current is never null when we need it — it previously
  // only rendered once audioUrl was set, which meant the very first
  // play() call raced against whether that re-render had actually
  // committed yet.
  useEffect(() => {
    if (!audioUrl || !autoplayRef.current) return
    autoplayRef.current = false
    audioRef.current?.play().catch((err) => {
      // Playback can legitimately be rejected (e.g. the browser decided
      // too much time passed since the click to count as user-initiated
      // autoplay) — previously this promise rejection went uncaught
      // entirely, so a failed play() looked identical to a silent no-op
      // with zero feedback. Now at least it's visible.
      console.error('Voice playback failed:', err)
      toast.error('Could not play this voice message')
    })
  }, [audioUrl, toast])

  const load = async () => {
    if (audioUrl || loading || !voiceNote) return false
    if (!sessionPassword) {
      toast.error('Unlock your session to play this voice message')
      return false
    }
    setLoading(true)
    try {
      const res = await api.get(`/voice/download/${voiceNote.id}`, {
        params: { password: sessionPassword },
        responseType: 'blob',
      })
      setAudioUrl(URL.createObjectURL(res.data))
      return true
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load voice message'))
      return false
    } finally {
      setLoading(false)
    }
  }

  const togglePlay = async () => {
    if (playing) {
      audioRef.current?.pause()
      return
    }
    if (audioUrl) {
      audioRef.current?.play().catch((err) => {
        console.error('Voice playback failed:', err)
        toast.error('Could not play this voice message')
      })
      return
    }
    autoplayRef.current = true
    const ok = await load()
    if (!ok) autoplayRef.current = false
  }

  if (!voiceNote) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner /> Loading voice message…
      </div>
    )
  }

  return (
    <div className="flex w-56 items-center gap-2.5">
      <button
        onClick={togglePlay}
        disabled={loading}
        aria-label={playing ? 'Pause' : 'Play voice message'}
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors
          ${isOwn ? 'bg-ink/15 hover:bg-ink/25' : 'bg-surface-hi hover:bg-surface-alt'}`}
      >
        {loading ? <Spinner /> : playing ? <PauseIcon /> : <PlayIcon />}
      </button>

      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-hi/60">
        <div className="h-full bg-signal transition-[width]" style={{ width: `${progress}%` }} />
      </div>

      <span className="w-9 shrink-0 text-right text-[0.7rem] text-muted">
        {voiceNote.duration_formatted || formatDuration(voiceNote.duration)}
      </span>

      <audio
        ref={audioRef}
        src={audioUrl || undefined}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false)
          setProgress(0)
        }}
        onTimeUpdate={(e) => {
          const { currentTime, duration } = e.target
          if (duration) setProgress((currentTime / duration) * 100)
        }}
        onError={() => {
          // Fires for decode/format errors, which a failed fetch would
          // never surface (the HTTP request already succeeded by the
          // time this fires) — previously nothing listened for this at
          // all, so a corrupted or mis-labeled recording just played
          // nothing with zero indication of why.
          console.error('Voice message failed to decode', audioRef.current?.error)
          toast.error("This voice message couldn't be played — it may be corrupted or in an unsupported format")
          setPlaying(false)
          if (audioUrl) URL.revokeObjectURL(audioUrl)
          setAudioUrl(null)
        }}
        className="hidden"
      />
    </div>
  )
}

function formatDuration(totalSeconds) {
  const m = Math.floor((totalSeconds || 0) / 60)
  const s = (totalSeconds || 0) % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function Spinner() {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5v14l11-7z" />
    </svg>
  )
}

function PauseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  )
}
