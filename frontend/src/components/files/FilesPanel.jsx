import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Spinner from '../common/Spinner.jsx'
import FileUploadModal from './FileUploadModal.jsx'

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`
}

export default function FilesPanel() {
  const { sessionPassword } = useAuth()
  const toast = useToast()
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [busyId, setBusyId] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/files/my-files')
      setFiles(res.data.files || [])
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load files'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const download = async (file) => {
    if (!sessionPassword) {
      toast.error('Unlock your session to decrypt this file')
      return
    }
    setBusyId(file.id)
    try {
      const res = await api.get(`/files/download/${file.id}`, {
        params: { password: sessionPassword },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = file.file_name
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Download failed'))
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (file) => {
    setBusyId(file.id)
    try {
      await api.delete(`/files/${file.id}`)
      setFiles((f) => f.filter((x) => x.id !== file.id))
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not delete file'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
        <p className="text-sm font-medium text-paper">Your files</p>
        <button
          onClick={() => setModalOpen(true)}
          className="rounded-md bg-signal-dim px-2.5 py-1 text-xs font-medium text-signal hover:brightness-110"
        >
          + Upload
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : files.length === 0 ? (
          <p className="px-2 py-8 text-center text-sm text-muted">
            No files yet. Everything you upload is encrypted with AES-256-GCM before it's stored.
          </p>
        ) : (
          <ul className="space-y-1">
            {files.map((file) => (
              <li key={file.id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-surface-alt">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-hi text-muted">
                  <FileIcon />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-paper">{file.file_name}</p>
                  <p className="truncate text-xs text-muted">{formatBytes(file.file_size)}</p>
                </div>
                {busyId === file.id ? (
                  <Spinner size={14} />
                ) : (
                  <>
                    <button
                      onClick={() => download(file)}
                      aria-label={`Download ${file.file_name}`}
                      className="rounded-md p-1.5 text-muted hover:bg-surface-hi hover:text-paper"
                    >
                      <DownloadIcon />
                    </button>
                    <button
                      onClick={() => remove(file)}
                      aria-label={`Delete ${file.file_name}`}
                      className="rounded-md p-1.5 text-muted hover:bg-danger-dim hover:text-danger"
                    >
                      ✕
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <FileUploadModal open={modalOpen} onClose={() => setModalOpen(false)} onUploaded={() => load()} />
    </div>
  )
}

function FileIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeLinejoin="round" />
      <path d="M14 2v6h6" strokeLinejoin="round" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 4v12M7 11l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 20h16" strokeLinecap="round" />
    </svg>
  )
}
