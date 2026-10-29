import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'
import { formatClock } from '../../utils/time'
import { blobErrorMessage } from './statusMedia.js'

const TEXT_DURATION_MS = 5000
const IMAGE_DURATION_MS = 6000

export default function StatusViewerModal({ entry, isOwn, onClose }) {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const statuses = entry.statuses
  const [index, setIndex] = useState(0)
  const [decrypted, setDecrypted] = useState(null)
  const [mediaUrl, setMediaUrl] = useState(null)
  const [mediaPct, setMediaPct] = useState(null)
  const [mediaFailed, setMediaFailed] = useState(false)
  const [muted, setMuted] = useState(false)
  const [loading, setLoading] = useState(true)
  const [paused, setPaused] = useState(false)
  const [progress, setProgress] = useState(0)
  const [viewers, setViewers] = useState(null)
  const rafRef = useRef(null)
  const startRef = useRef(0)
  const elapsedRef = useRef(0)
  const videoRef = useRef(null)

  const current = statuses[index]
  const isVideo = current?.media_type === 'video'
  const isImage = current?.media_type === 'image'

  const goTo = (nextIndex) => {
    if (nextIndex < 0) return
    if (nextIndex >= statuses.length) {
      onClose()
      return
    }
    setIndex(nextIndex)
  }

  // Load + decrypt the current status whenever it changes.
  useEffect(() => {
    if (!current) return undefined
    if (!sessionPassword) {
      toast.error('Unlock your session to view this status')
      onClose()
      return undefined
    }
    let cancelled = false
    setLoading(true)
    setDecrypted(null)
    setMediaUrl(null)
    setMediaPct(null)
    setMediaFailed(false)
    setProgress(0)
    setViewers(null)

    api
      .get(`/status/${current.id}`, { params: { password: sessionPassword } })
      .then((res) => {
        if (cancelled) return null
        setDecrypted(res.data.status)
        if (!res.data.status.media_type) return null
        // POST (not GET) so the password never appears in a URL.
        return api.post(
          `/status/${current.id}/media`,
          { password: sessionPassword },
          {
            responseType: 'blob',
            onDownloadProgress: (e) => {
              if (!cancelled && e.total) setMediaPct(Math.round((e.loaded / e.total) * 100))
            },
          },
        )
      })
      .then((mediaRes) => {
        if (cancelled || !mediaRes) return
        setMediaUrl(URL.createObjectURL(mediaRes.data))
      })
      .catch(async (err) => {
        if (cancelled) return
        toast.error(await blobErrorMessage(err, extractErrorMessage(err, 'Could not load this status')))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, sessionPassword])

  useEffect(() => {
    return () => {
      if (mediaUrl) URL.revokeObjectURL(mediaUrl)
    }
  }, [mediaUrl])

  // Progress bar. Text and photos run on a timer; a video's bar follows the
  // video itself (and the status advances when it ends, see onEnded below).
  useEffect(() => {
    if (loading || !current) return undefined

    if (isVideo) {
      let last = -1
      const follow = () => {
        const v = videoRef.current
        if (v && v.duration) {
          const pct = Math.min(100, (v.currentTime / v.duration) * 100)
          // Only repaint when the bar moves visibly (not 60 times a second).
          if (Math.abs(pct - last) >= 0.25 || pct >= 100) {
            last = pct
            setProgress(pct)
          }
        }
        rafRef.current = requestAnimationFrame(follow)
      }
      rafRef.current = requestAnimationFrame(follow)
      return () => cancelAnimationFrame(rafRef.current)
    }

    if (paused) return undefined
    const duration = isImage ? IMAGE_DURATION_MS : TEXT_DURATION_MS
    startRef.current = performance.now() - elapsedRef.current

    const tick = (now) => {
      const elapsed = now - startRef.current
      elapsedRef.current = elapsed
      const pct = Math.min(100, (elapsed / duration) * 100)
      setProgress(pct)
      if (pct >= 100) {
        elapsedRef.current = 0
        goTo(index + 1)
        return
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, paused, index, current?.id, isVideo, isImage])

  useEffect(() => {
    elapsedRef.current = 0
  }, [index])

  // Holding the screen pauses a video the same way it pauses the timer.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (paused) v.pause()
    else v.play().catch(() => {})
  }, [paused, mediaUrl])

  useEffect(() => {
    if (videoRef.current) videoRef.current.muted = muted
  }, [muted, mediaUrl])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') goTo(index + 1)
      if (e.key === 'ArrowLeft') goTo(index - 1)
      if (e.key === 'm' || e.key === 'M') setMuted((m) => !m)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index])

  // Start playback with sound; if the browser's autoplay policy refuses,
  // fall back to muted (the sound button then offers to turn it on).
  const startVideo = (v) => {
    if (paused) return
    const attempt = v.play()
    if (attempt?.catch) {
      attempt.catch(() => {
        v.muted = true
        setMuted(true)
        v.play().catch(() => {})
      })
    }
  }

  const loadViewers = async () => {
    if (viewers) return
    try {
      const res = await api.get(`/status/${current.id}/viewers`)
      setViewers(res.data.viewers || [])
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load viewers'))
    }
  }

  const deleteStatus = async () => {
    if (!window.confirm('Delete this status?')) return
    try {
      await api.delete(`/status/${current.id}`)
      toast.info('Status deleted')
      if (statuses.length === 1) {
        onClose()
      } else {
        goTo(index === statuses.length - 1 ? index - 1 : index)
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not delete status'))
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black">
      <div className="relative flex h-full w-full max-w-md flex-col overflow-hidden bg-surface sm:h-[92vh] sm:rounded-2xl">
        {/* Progress segments */}
        <div className="absolute left-0 right-0 top-0 z-20 flex gap-1 p-2">
          {statuses.map((s, i) => (
            <div key={s.id} className="h-1 flex-1 overflow-hidden rounded-full bg-paper/25">
              <div
                className="h-full bg-paper transition-[width]"
                style={{
                  width: i < index ? '100%' : i === index ? `${progress}%` : '0%',
                  transitionDuration: i === index ? '0ms' : '150ms',
                }}
              />
            </div>
          ))}
        </div>

        {/* Header */}
        <div className="absolute left-0 right-0 top-4 z-20 flex items-center gap-2.5 px-3 pt-2">
          <Avatar name={entry.user.full_name || entry.user.username} src={entry.user.profile_picture} size={34} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-paper">{entry.user.full_name || entry.user.username}</p>
            {decrypted && <p className="text-xs text-paper/70">{formatClock(decrypted.created_at)}</p>}
          </div>
          {isOwn && (
            <button onClick={deleteStatus} aria-label="Delete status" className="rounded-full p-1.5 text-paper/80 hover:bg-ink/30">
              <TrashIcon />
            </button>
          )}
          <button onClick={onClose} aria-label="Close" className="rounded-full p-1.5 text-paper/80 hover:bg-ink/30">
            ✕
          </button>
        </div>

        {/* Content */}
        <div
          className="relative flex flex-1 items-center justify-center overflow-hidden"
          style={{ backgroundColor: !mediaUrl ? current?.background_color || '#151D22' : undefined }}
          onMouseDown={() => setPaused(true)}
          onMouseUp={() => setPaused(false)}
          onTouchStart={() => setPaused(true)}
          onTouchEnd={() => setPaused(false)}
        >
          {loading ? (
            <div className="flex flex-col items-center gap-3">
              <Spinner size={28} />
              {isVideo && (
                <p className="text-xs text-paper/70">
                  {mediaPct === null ? 'Decrypting video…' : `Loading video ${mediaPct}%`}
                </p>
              )}
            </div>
          ) : mediaUrl && isVideo ? (
            mediaFailed ? (
              <div className="flex flex-col items-center gap-3 px-8 text-center">
                <p className="text-sm text-paper">This video can’t be played in your browser.</p>
                <a
                  href={mediaUrl}
                  download={`status-${current.id}`}
                  className="relative z-30 rounded-lg bg-surface-hi px-3 py-1.5 text-xs font-medium text-paper hover:brightness-110"
                >
                  Download it instead
                </a>
              </div>
            ) : (
              <video
                key={mediaUrl}
                ref={videoRef}
                src={mediaUrl}
                className="max-h-full max-w-full object-contain"
                playsInline
                preload="auto"
                onCanPlay={(e) => startVideo(e.currentTarget)}
                onEnded={() => goTo(index + 1)}
                onError={() => setMediaFailed(true)}
              />
            )
          ) : mediaUrl ? (
            <img src={mediaUrl} alt="" className="max-h-full max-w-full object-contain" />
          ) : (
            <p className="whitespace-pre-wrap break-words px-8 text-center text-2xl font-medium text-paper">
              {decrypted?.caption}
            </p>
          )}

          {/* Tap zones */}
          <button
            onClick={() => goTo(index - 1)}
            aria-label="Previous status"
            className="absolute left-0 top-0 h-full w-1/3 cursor-default"
          />
          <button
            onClick={() => goTo(index + 1)}
            aria-label="Next status"
            className="absolute right-0 top-0 h-full w-1/3 cursor-default"
          />
        </div>

        {/* Caption overlay for photo and video posts */}
        {mediaUrl && decrypted?.caption && (
          <div className="pointer-events-none absolute bottom-0 left-0 right-0 bg-gradient-to-t from-ink/80 to-transparent px-4 pb-16 pt-10">
            <p className="whitespace-pre-wrap break-words text-sm text-paper">{decrypted.caption}</p>
          </div>
        )}

        {/* Sound toggle (videos only) */}
        {mediaUrl && isVideo && !mediaFailed && (
          <button
            onClick={() => setMuted((m) => !m)}
            aria-label={muted ? 'Turn sound on' : 'Mute'}
            aria-pressed={muted}
            className={`absolute right-3 z-30 rounded-full bg-ink/60 p-2.5 text-paper hover:bg-ink/80 ${isOwn ? 'bottom-14' : 'bottom-4'}`}
          >
            {muted ? <MutedIcon /> : <SoundIcon />}
          </button>
        )}

        {/* Seen-by footer, own status only */}
        {isOwn && (
          <button
            onClick={loadViewers}
            className="border-t border-line px-4 py-2.5 text-left text-xs text-muted hover:text-paper"
          >
            {viewers === null ? (
              'Tap to see who viewed this'
            ) : viewers.length === 0 ? (
              'No views yet'
            ) : (
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {viewers.map((v) => (
                  <span key={v.id} className="text-paper">
                    {v.full_name || v.username}
                  </span>
                ))}
              </span>
            )}
          </button>
        )}
      </div>
    </div>,
    document.body,
  )
}

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SoundIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  )
}

function MutedIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="m22 9-6 6M16 9l6 6" />
    </svg>
  )
}
