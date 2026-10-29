import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function Modal({ open, onClose, title, children, wide = false }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleKey)
    dialogRef.current?.focus()
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/70 backdrop-blur-sm sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={dialogRef}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={`max-h-[85vh] w-full overflow-y-auto rounded-t-2xl border border-line bg-surface p-5 shadow-2xl sm:rounded-2xl ${wide ? 'sm:max-w-lg' : 'sm:max-w-sm'} sm:m-4`}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-paper">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-md p-1 text-muted hover:bg-surface-alt hover:text-paper"
          >
            <CloseIcon />
          </button>
        </div>
        {children}
      </div>
      {/* Click-catcher backdrop, kept behind the stopPropagation'd panel */}
      <button
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 -z-10 cursor-default"
      />
    </div>,
    document.body,
  )
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
    </svg>
  )
}
