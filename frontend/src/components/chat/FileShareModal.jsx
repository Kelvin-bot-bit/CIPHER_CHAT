import { useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Modal from '../common/Modal.jsx'
import Spinner from '../common/Spinner.jsx'

const MAX_MB = 100

// Shares a file inside a specific conversation: sends a message first (so a
// message_id exists), then uploads the file linked to it via /files/upload's
// message_id param — that's what makes it show up as an attachment on that
// message rather than sitting in the standalone file vault.
export default function FileShareModal({ open, onClose, chat, onSent }) {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [caption, setCaption] = useState('')
  const [sending, setSending] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!open) {
      setFile(null)
      setCaption('')
      setProgress(0)
    }
  }, [open])

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const acceptFile = (f) => {
    if (!f) return
    if (f.size > MAX_MB * 1024 * 1024) {
      toast.error(`Files must be under ${MAX_MB}MB`)
      return
    }
    setFile(f)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    acceptFile(e.dataTransfer.files?.[0])
  }

  const send = async () => {
    if (!file || !sessionPassword) return
    setSending(true)
    setProgress(0)
    try {
      // 1. Create the message that will carry this attachment. The backend
      //    requires non-empty message text, so fall back to a 📎 + filename
      //    caption when the user didn't type one.
      const sendRes = await api.post('/messages/send', {
        recipient_id: chat.id,
        recipient_type: chat.type,
        message: caption.trim() || `📎 ${file.name}`,
        password: sessionPassword,
        message_type: 'file',
      })
      const messageId = sendRes.data.message_id

      // 2. Upload the file linked to that message.
      const form = new FormData()
      form.append('file', file)
      form.append('password', sessionPassword)
      form.append('message_id', messageId)
      await api.post('/files/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100))
        },
      })

      onSent?.()
      onClose()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not share file'))
    } finally {
      setSending(false)
      setProgress(0)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Share a file with ${chat?.name || ''}`}>
      <div className="space-y-4">
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`rounded-xl border border-dashed px-4 py-6 text-center transition-colors ${dragOver ? 'border-signal bg-signal-dim/30' : 'border-line'}`}
        >
          {previewUrl ? (
            <div className="flex flex-col items-center gap-2">
              <img src={previewUrl} alt="" className="max-h-32 rounded-lg object-contain" />
              <span className="text-sm text-paper">{file.name}</span>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex w-full flex-col items-center gap-2"
            >
              <UploadIcon />
              <span className="text-sm text-paper">{file ? file.name : 'Click or drag a file here'}</span>
              <span className="text-xs text-muted">Up to {MAX_MB}MB · encrypted before storage</span>
            </button>
          )}
          {file && (
            <button
              onClick={() => setFile(null)}
              className="mt-2 text-xs text-muted underline-offset-2 hover:text-paper hover:underline"
            >
              Choose a different file
            </button>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          onChange={(e) => acceptFile(e.target.files?.[0])}
          className="hidden"
        />

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Caption (optional)</span>
          <input
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder={file ? file.name : 'Say something about this file…'}
            className="w-full rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50"
          />
        </label>

        {!sessionPassword && (
          <p className="rounded-lg bg-amber-dim px-3 py-2 text-xs text-amber">
            Unlock your session first — sending a file also needs your password, same as a message.
          </p>
        )}

        {sending && (
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-alt">
            <div className="h-full bg-signal transition-all duration-150" style={{ width: `${progress}%` }} />
          </div>
        )}

        <button
          onClick={send}
          disabled={!file || sending || !sessionPassword}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
        >
          {sending && <Spinner size={14} />}
          {sending ? `Sending… ${progress}%` : 'Send file'}
        </button>
      </div>
    </Modal>
  )
}

function UploadIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-muted" strokeWidth="2">
      <path d="M12 16V4M7 9l5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
