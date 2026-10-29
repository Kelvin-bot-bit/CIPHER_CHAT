import { useState } from 'react'
import SecurityBadge from '../common/SecurityBadge.jsx'
import VoicePlayer from './VoicePlayer.jsx'
import { formatClock, formatCountdown } from '../../utils/time'

const QUICK_REACTIONS = ['👍', '❤️', '😂', '😮', '😢', '🙏']

export default function MessageBubble({ message, isOwn, showSender, senderName, onEdit, onDelete, onReply, onReact, attachment, attachmentFailed, onRetryAttachment, onDownloadFile, downloadingFile, voiceNote }) {
  const [showActions, setShowActions] = useState(false)
  const [showReactionPicker, setShowReactionPicker] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(message.message || '')

  const failed = message.message === '[Unable to decrypt]' || !message.message

  const submitEdit = () => {
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== message.message) onEdit?.(message.id, trimmed)
    setEditing(false)
  }

  const reactionEntries = Object.entries(message.reactions || {}).filter(([, count]) => count > 0)

  return (
    <div
      className={`group flex ${isOwn ? 'justify-end' : 'justify-start'}`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => {
        setShowActions(false)
        setShowReactionPicker(false)
      }}
    >
      <div className={`flex max-w-[78%] items-end gap-1.5 sm:max-w-[65%] ${isOwn ? 'flex-row-reverse' : ''}`}>
        <div className={`flex flex-col gap-1 ${isOwn ? 'items-end' : 'items-start'}`}>
          {showSender && !isOwn && <span className="px-1 text-xs font-medium text-muted">{senderName}</span>}

          {editing ? (
            <div className="w-64 space-y-1.5">
              <textarea
                autoFocus
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-signal/40 bg-surface-alt px-2.5 py-1.5 text-sm text-paper"
              />
              <div className="flex justify-end gap-1.5 text-xs">
                <button onClick={() => setEditing(false)} className="rounded-md px-2 py-1 text-muted hover:bg-surface-alt">
                  Cancel
                </button>
                <button onClick={submitEdit} className="rounded-md bg-signal px-2 py-1 font-medium text-ink">
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div
              className={`rounded-chat px-3.5 py-2 text-[0.925rem] leading-relaxed shadow-sm
                ${isOwn ? 'rounded-br-sm bg-signal-dim text-paper' : 'rounded-bl-sm bg-surface-hi text-paper'}
                ${failed && !message.is_deleted ? 'border border-dashed border-danger/50 text-danger' : ''}
              `}
            >
              {message.is_deleted ? (
                <em className="text-muted">This message was deleted</em>
              ) : message.message_type === 'voice' ? (
                <VoicePlayer voiceNote={voiceNote} isOwn={isOwn} />
              ) : (
                <>
                  {message.file_url && (
                    <FileAttachmentCard
                      attachment={attachment}
                      failed={attachmentFailed}
                      onRetry={onRetryAttachment}
                      onDownload={onDownloadFile}
                      downloading={downloadingFile}
                      isOwn={isOwn}
                    />
                  )}
                  <span className="whitespace-pre-wrap break-words">{message.message || 'Unable to decrypt'}</span>
                </>
              )}
              {message.is_edited && !message.is_deleted && (
                <span className="ml-1.5 text-[0.7rem] text-muted">(edited)</span>
              )}
            </div>
          )}

          {reactionEntries.length > 0 && (
            <div className="flex flex-wrap gap-1 px-1">
              {reactionEntries.map(([emoji, count]) => (
                <button
                  key={emoji}
                  onClick={() => onReact?.(message.id, emoji)}
                  className="rounded-full border border-line bg-surface-alt px-1.5 py-0.5 text-xs hover:border-signal/40"
                >
                  {emoji} <span className="text-muted">{count}</span>
                </button>
              ))}
            </div>
          )}

          <div className={`flex items-center gap-1.5 px-1 text-[0.68rem] text-muted ${isOwn ? 'flex-row-reverse' : ''}`}>
            <SecurityBadge verified={message.is_valid_signature} />
            <span>{formatClock(message.created_at)}</span>
            {message.expires_at && (
              <span className="flex items-center gap-0.5 text-amber" title="Disappearing message">
                <TimerGlyph />
                {formatCountdown(message.expires_at)}
              </span>
            )}
          </div>
        </div>

        {!message.is_deleted && !editing && (
          <div className={`relative flex shrink-0 gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 ${showActions ? 'opacity-100' : ''}`}>
            <button
              onClick={() => setShowReactionPicker((s) => !s)}
              aria-label="React"
              className="rounded-md p-1 text-muted hover:bg-surface-alt hover:text-paper"
            >
              <ReactIcon />
            </button>
            <button
              onClick={() => onReply?.(message)}
              aria-label="Reply"
              className="rounded-md p-1 text-muted hover:bg-surface-alt hover:text-paper"
            >
              <ReplyIcon />
            </button>
            {isOwn && (
              <>
                <button
                  onClick={() => setEditing(true)}
                  aria-label="Edit"
                  className="rounded-md p-1 text-muted hover:bg-surface-alt hover:text-paper"
                >
                  <EditIcon />
                </button>
                <button
                  onClick={() => onDelete?.(message.id)}
                  aria-label="Delete"
                  className="rounded-md p-1 text-muted hover:bg-danger-dim hover:text-danger"
                >
                  <DeleteIcon />
                </button>
              </>
            )}

            {showReactionPicker && (
              <div className={`absolute top-7 z-10 flex gap-0.5 rounded-full border border-line bg-surface-hi p-1 shadow-lg ${isOwn ? 'right-0' : 'left-0'}`}>
                {QUICK_REACTIONS.map((emoji) => (
                  <button
                    key={emoji}
                    onClick={() => {
                      onReact?.(message.id, emoji)
                      setShowReactionPicker(false)
                    }}
                    className="rounded-full p-1 text-base hover:scale-125 hover:bg-surface-alt"
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function formatBytes(bytes) {
  if (!bytes) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`
}

function FileAttachmentCard({ attachment, failed, onRetry, onDownload, downloading, isOwn }) {
  const isImage = attachment?.mime_type?.startsWith('image/')

  if (failed) {
    return (
      <button
        onClick={onRetry}
        className={`mb-1.5 flex w-full items-center gap-2.5 rounded-lg border border-dashed border-danger/40 px-2.5 py-2 text-left text-danger transition-colors hover:bg-danger-dim`}
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-danger-dim">
          <WarningIcon />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm">Couldn't load this attachment</span>
          <span className="block text-[0.7rem] opacity-80">Tap to retry</span>
        </span>
      </button>
    )
  }

  return (
    <button
      onClick={() => attachment && !downloading && onDownload?.(attachment.id, attachment.file_name)}
      disabled={!attachment || downloading}
      className={`mb-1.5 flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-colors
        ${isOwn ? 'border-signal/20 bg-ink/10 hover:bg-ink/20' : 'border-line bg-surface-alt hover:bg-surface-hi'}
        disabled:cursor-wait`}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-hi text-muted">
        {downloading ? <SpinnerGlyph /> : isImage ? <ImageIcon /> : <FileIcon />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm">
          {downloading ? 'Downloading…' : attachment?.file_name || 'Loading attachment…'}
        </span>
        {attachment?.file_size ? <span className="block text-[0.7rem] text-muted">{formatBytes(attachment.file_size)}</span> : null}
      </span>
      {attachment && <DownloadIcon />}
    </button>
  )
}

function FileIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeLinejoin="round" />
      <path d="M14 2v6h6" strokeLinejoin="round" />
    </svg>
  )
}

function ImageIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="m21 15-5-5L5 21" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 text-muted">
      <path d="M12 4v12M7 11l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 20h16" strokeLinecap="round" />
    </svg>
  )
}

function ReactIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01" strokeLinecap="round" />
    </svg>
  )
}

function ReplyIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 10 4 15l5 5M4 15h11a4 4 0 0 0 4-4V5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function EditIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DeleteIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TimerGlyph() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.5 2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function WarningIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 9v4M12 17h.01M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SpinnerGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="animate-spin">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
