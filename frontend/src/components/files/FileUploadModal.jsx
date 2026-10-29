import { useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Modal from '../common/Modal.jsx'
import Spinner from '../common/Spinner.jsx'

const MAX_MB = 100

export default function FileUploadModal({ open, onClose, onUploaded }) {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)

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

  const pick = (e) => acceptFile(e.target.files?.[0])

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    acceptFile(e.dataTransfer.files?.[0])
  }

  const upload = async () => {
    if (!file || !sessionPassword) return
    setUploading(true)
    setProgress(0)
    const form = new FormData()
    form.append('file', file)
    form.append('password', sessionPassword)
    try {
      const res = await api.post('/files/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100))
        },
      })
      toast.success('File uploaded and encrypted')
      onUploaded?.(res.data.file)
      setFile(null)
      onClose()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Upload failed'))
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Upload a file">
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
              <span className="text-xs text-muted">Up to {MAX_MB}MB · encrypted with AES-256-GCM before storage</span>
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
        <input ref={inputRef} type="file" onChange={pick} className="hidden" />

        {!sessionPassword && (
          <p className="rounded-lg bg-amber-dim px-3 py-2 text-xs text-amber">
            Unlock your session first — file encryption needs your password too.
          </p>
        )}

        {uploading && (
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-alt">
            <div className="h-full bg-signal transition-all duration-150" style={{ width: `${progress}%` }} />
          </div>
        )}

        <button
          onClick={upload}
          disabled={!file || uploading || !sessionPassword}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
        >
          {uploading && <Spinner size={14} />}
          {uploading ? `Uploading… ${progress}%` : 'Upload'}
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
