import { useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Modal from '../common/Modal.jsx'
import Spinner from '../common/Spinner.jsx'

const MAX_SECONDS = 120

// Chrome/Firefox/Edge (desktop and Android) reliably support
// audio/webm;codecs=opus via MediaRecorder — that's what this always
// requests. Safari/iOS MediaRecorder audio support is inconsistent, so
// recording (or playing back someone else's recording) may not work there.
// Not something the frontend can paper over; flagged here and in the
// backend's download endpoint rather than silently producing broken audio.
const PREFERRED_MIME = 'audio/webm;codecs=opus'

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return null
  if (MediaRecorder.isTypeSupported(PREFERRED_MIME)) return PREFERRED_MIME
  if (MediaRecorder.isTypeSupported('audio/webm')) return 'audio/webm'
  // Previously returned '' here — falsy, so the `mimeType === null` check
  // above never caught it, and the recording proceeded silently with
  // whatever default format the browser's MediaRecorder happened to pick.
  // The blob then got labeled 'audio/webm' regardless (see the `|| 'audio/webm'`
  // fallback below) even when the actual bytes weren't webm at all — and
  // the backend's download endpoint always serves it back labeled
  // audio/webm too, so a mismatched recording would silently fail to
  // decode on playback with no error surfaced anywhere. Returning null
  // here instead means the unsupported-browser path actually triggers,
  // rather than producing a file that looks fine but never plays.
  return null
}

export default function VoiceRecorderModal({ open, onClose, chat, onSent }) {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState('idle') // idle | recording | recorded | sending
  const [seconds, setSeconds] = useState(0)
  const [audioBlob, setAudioBlob] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [unsupported, setUnsupported] = useState(false)

  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)
  const timerRef = useRef(null)

  const reset = () => {
    setStatus('idle')
    setSeconds(0)
    setAudioBlob(null)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
    chunksRef.current = []
  }

  useEffect(() => {
    if (!open) {
      reset()
      streamRef.current?.getTracks().forEach((t) => t.stop())
      clearInterval(timerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((t) => t.stop())
      clearInterval(timerRef.current)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  const startRecording = async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setUnsupported(true)
      return
    }
    const mimeType = pickMimeType()
    if (mimeType === null) {
      setUnsupported(true)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
        setAudioBlob(blob)
        setPreviewUrl(URL.createObjectURL(blob))
        setStatus('recorded')
        stream.getTracks().forEach((t) => t.stop())
      }

      recorder.start()
      setStatus('recording')
      setSeconds(0)
      timerRef.current = setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= MAX_SECONDS) {
            recorder.stop()
            clearInterval(timerRef.current)
            return MAX_SECONDS
          }
          return s + 1
        })
      }, 1000)
    } catch (err) {
      toast.error('Microphone access was denied or unavailable')
    }
  }

  const stopRecording = () => {
    clearInterval(timerRef.current)
    mediaRecorderRef.current?.stop()
  }

  const send = async () => {
    if (!audioBlob || !sessionPassword) return
    setStatus('sending')
    try {
      const sendRes = await api.post('/messages/send', {
        recipient_id: chat.id,
        recipient_type: chat.type,
        message: `🎤 Voice message (${formatDuration(seconds)})`,
        password: sessionPassword,
        message_type: 'voice',
      })
      const messageId = sendRes.data.message_id

      const form = new FormData()
      const ext = audioBlob.type.includes('webm') ? 'webm' : 'ogg'
      form.append('audio', audioBlob, `voice.${ext}`)
      form.append('message_id', messageId)
      form.append('duration', String(seconds))
      // Only actually needed server-side for a group chat (to unwrap the
      // group's key so the recording's key can be wrapped with it too) —
      // harmless to always send, direct chats just ignore it.
      form.append('password', sessionPassword)
      await api.post('/voice/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      onSent?.()
      onClose()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not send voice message'))
      setStatus('recorded')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Voice message to ${chat?.name || ''}`}>
      {unsupported ? (
        <p className="rounded-lg bg-amber-dim px-3 py-3 text-sm text-amber">
          Voice recording isn't supported in this browser. It reliably works in Chrome, Firefox, and Edge —
          Safari's support for this is inconsistent.
        </p>
      ) : (
        <div className="flex flex-col items-center gap-5 py-4">
          <div className="font-mono text-3xl text-paper">{formatDuration(seconds)}</div>

          {status === 'idle' && (
            <button
              onClick={startRecording}
              aria-label="Start recording"
              className="flex h-16 w-16 items-center justify-center rounded-full bg-danger text-paper shadow-lg transition-transform hover:scale-105"
            >
              <MicIcon />
            </button>
          )}

          {status === 'recording' && (
            <>
              <span className="flex items-center gap-2 text-sm text-danger">
                <span className="h-2 w-2 animate-pulseDot rounded-full bg-danger" /> Recording…
              </span>
              <button
                onClick={stopRecording}
                aria-label="Stop recording"
                className="flex h-16 w-16 items-center justify-center rounded-full bg-surface-hi text-paper shadow-lg transition-transform hover:scale-105"
              >
                <StopIcon />
              </button>
            </>
          )}

          {(status === 'recorded' || status === 'sending') && previewUrl && (
            <div className="w-full space-y-3">
              <audio controls src={previewUrl} className="w-full" />
              <div className="flex gap-2">
                <button
                  onClick={reset}
                  disabled={status === 'sending'}
                  className="flex-1 rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110 disabled:opacity-60"
                >
                  Re-record
                </button>
                <button
                  onClick={send}
                  disabled={status === 'sending' || !sessionPassword}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-signal px-3 py-2 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
                >
                  {status === 'sending' && <Spinner size={14} />}
                  Send
                </button>
              </div>
            </div>
          )}

          {!sessionPassword && (
            <p className="w-full rounded-lg bg-amber-dim px-3 py-2 text-center text-xs text-amber">
              Unlock your session first — sending a voice message also needs your password.
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}

function formatDuration(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function MicIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 19v3" strokeLinecap="round" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  )
}
