import { useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Modal from '../common/Modal.jsx'
import Spinner from '../common/Spinner.jsx'
import {
  MAX_IMAGE_MB,
  MAX_VIDEO_MB,
  MAX_VIDEO_SECONDS,
  MEDIA_ACCEPT,
  formatDuration,
  formatSize,
  kindOf,
  probeVideo,
} from './statusMedia.js'

const BACKGROUNDS = ['#151D22', '#2C4A42', '#4A3B23', '#233B4A', '#3B234A', '#4A2328']

export default function StatusComposerModal({ open, onClose, onPosted }) {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const [caption, setCaption] = useState('')
  const [background, setBackground] = useState(BACKGROUNDS[0])
  const [media, setMedia] = useState(null) // { file, kind: 'image' | 'video', duration? }
  const [previewUrl, setPreviewUrl] = useState(null)
  const [checking, setChecking] = useState(false)
  const [posting, setPosting] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    if (!open) {
      abortRef.current?.abort()
      setCaption('')
      setMedia(null)
      setBackground(BACKGROUNDS[0])
      setUploadPct(0)
      setPosting(false)
    }
  }, [open])

  useEffect(() => {
    if (!media) {
      setPreviewUrl(null)
      return undefined
    }
    const url = URL.createObjectURL(media.file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [media])

  const acceptFile = async (file) => {
    if (!file) return
    const kind = kindOf(file)
    if (!kind) {
      toast.error('Use a JPEG, PNG, GIF, WebP or AVIF photo, or an MP4, MOV or WebM video')
      return
    }

    if (kind === 'image') {
      if (file.size > MAX_IMAGE_MB * 1024 * 1024) {
        toast.error(`Photos must be under ${MAX_IMAGE_MB} MB (this one is ${formatSize(file.size)})`)
        return
      }
      setMedia({ file, kind })
      return
    }

    // Video: check size first (instant), then length/readability (reads only the header).
    if (file.size > MAX_VIDEO_MB * 1024 * 1024) {
      toast.error(`Videos must be under ${MAX_VIDEO_MB} MB (this one is ${formatSize(file.size)}). Try trimming it.`)
      return
    }
    setChecking(true)
    try {
      const info = await probeVideo(file)
      if (info.duration > MAX_VIDEO_SECONDS + 0.5) {
        toast.error(
          `Status videos can be up to ${MAX_VIDEO_SECONDS} seconds (this one is ${formatDuration(info.duration)}). Trim it and try again.`,
        )
        return
      }
      setMedia({ file, kind, duration: info.duration })
    } catch (err) {
      toast.error(
        err.message === 'no-video'
          ? 'That file has no picture. Choose a video with visuals.'
          : "Your browser can't read that video. Try an MP4 (H.264) or WebM file.",
      )
    } finally {
      setChecking(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    acceptFile(e.dataTransfer.files?.[0])
  }

  const post = async () => {
    if (!sessionPassword) {
      toast.error('Unlock your session to post a status')
      return
    }
    if (!caption.trim() && !media) {
      toast.error('Add some text, a photo or a video first')
      return
    }
    setPosting(true)
    setUploadPct(0)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const form = new FormData()
      form.append('caption', caption.trim())
      form.append('password', sessionPassword)
      if (media) {
        form.append('media', media.file)
      } else {
        form.append('background_color', background)
      }
      await api.post('/status/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        signal: controller.signal,
        onUploadProgress: (e) => {
          if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100))
        },
      })
      toast.success('Status posted — visible to friends for 24 hours')
      onPosted?.()
      onClose()
    } catch (err) {
      if (controller.signal.aborted) return
      toast.error(extractErrorMessage(err, 'Could not post status'))
    } finally {
      abortRef.current = null
      setPosting(false)
    }
  }

  const uploading = posting && media
  const label = !posting
    ? 'Post status'
    : uploadPct >= 100
      ? 'Encrypting and sharing…'
      : media
        ? `Uploading ${uploadPct}%`
        : 'Posting…'

  return (
    <Modal open={open} onClose={onClose} title="Post a status">
      <div className="space-y-4">
        {previewUrl && media ? (
          <div className="relative overflow-hidden rounded-xl bg-black">
            {media.kind === 'video' ? (
              <video
                src={previewUrl}
                className="max-h-72 w-full object-contain"
                autoPlay
                muted
                loop
                playsInline
                controls
              />
            ) : (
              <img src={previewUrl} alt="" className="max-h-72 w-full object-cover" />
            )}
            {media.kind === 'video' && (
              <span className="pointer-events-none absolute left-2 top-2 rounded-full bg-ink/70 px-2 py-1 text-xs text-paper">
                {formatDuration(media.duration)} · {formatSize(media.file.size)}
              </span>
            )}
            <button
              onClick={() => setMedia(null)}
              disabled={posting}
              className="absolute right-2 top-2 rounded-full bg-ink/70 p-1.5 text-paper hover:bg-ink disabled:opacity-50"
              aria-label={media.kind === 'video' ? 'Remove video' : 'Remove photo'}
            >
              ✕
            </button>
          </div>
        ) : (
          <div
            className={`flex flex-col items-center gap-2 rounded-xl px-4 py-8 text-center transition-shadow ${dragOver ? 'ring-2 ring-signal' : ''}`}
            style={{ backgroundColor: background }}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <p className="whitespace-pre-wrap break-words text-center text-lg font-medium text-paper">
              {caption || 'Your status text will look like this'}
            </p>
            <p className="text-xs text-paper/60">
              {dragOver ? 'Drop to add it' : 'Or drop a photo or video here'}
            </p>
          </div>
        )}

        <textarea
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          rows={2}
          maxLength={500}
          placeholder={media ? 'Add a caption (optional)' : "What's on your mind?"}
          className="w-full resize-none rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50"
        />

        {!media && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted">Background</p>
            <div className="flex gap-2">
              {BACKGROUNDS.map((color) => (
                <button
                  key={color}
                  onClick={() => setBackground(color)}
                  aria-label={`Use background ${color}`}
                  className={`h-7 w-7 rounded-full border-2 ${background === color ? 'border-signal' : 'border-transparent'}`}
                  style={{ backgroundColor: color }}
                />
              ))}
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={checking || posting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110 disabled:opacity-60"
          >
            {checking && <Spinner size={14} />}
            {checking ? 'Checking video…' : media ? 'Change photo or video' : 'Add photo or video'}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={MEDIA_ACCEPT}
            onChange={(e) => {
              acceptFile(e.target.files?.[0])
              e.target.value = '' // lets the same file be picked again after removing it
            }}
            className="hidden"
          />
          {!media && (
            <p className="text-center text-xs text-muted">
              Photos up to {MAX_IMAGE_MB} MB · videos up to {MAX_VIDEO_SECONDS} seconds and {MAX_VIDEO_MB} MB
            </p>
          )}
        </div>

        {!sessionPassword && (
          <p className="rounded-lg bg-amber-dim px-3 py-2 text-xs text-amber">
            Unlock your session first — posting a status needs your password too.
          </p>
        )}

        <button
          onClick={post}
          disabled={posting || checking || !sessionPassword}
          className="relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
        >
          {uploading && (
            <span
              className="absolute inset-y-0 left-0 bg-ink/15 transition-[width] duration-200"
              style={{ width: `${uploadPct}%` }}
              aria-hidden="true"
            />
          )}
          <span className="relative flex items-center gap-2">
            {posting && <Spinner size={14} />}
            {label}
          </span>
        </button>
      </div>
    </Modal>
  )
}
