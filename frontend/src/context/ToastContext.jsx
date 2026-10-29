import { createContext, useCallback, useContext, useRef, useState } from 'react'

const ToastContext = createContext(null)

let idCounter = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef({})

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((toast) => toast.id !== id))
    clearTimeout(timers.current[id])
    delete timers.current[id]
  }, [])

  const push = useCallback(
    (message, { tone = 'default', duration = 4200 } = {}) => {
      const id = ++idCounter
      setToasts((t) => [...t, { id, message, tone }])
      timers.current[id] = setTimeout(() => dismiss(id), duration)
      return id
    },
    [dismiss],
  )

  const toast = {
    show: push,
    success: (m, opts) => push(m, { ...opts, tone: 'success' }),
    error: (m, opts) => push(m, { ...opts, tone: 'danger' }),
    info: (m, opts) => push(m, { ...opts, tone: 'default' }),
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[100] flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 sm:bottom-6 sm:right-6"
        role="status"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            onClick={() => dismiss(t.id)}
            className={`cursor-pointer rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur transition-all
              ${t.tone === 'success' ? 'border-signal/40 bg-signal-dim/90 text-signal' : ''}
              ${t.tone === 'danger' ? 'border-danger/40 bg-danger-dim/90 text-danger' : ''}
              ${t.tone === 'default' ? 'border-line bg-surface-hi/95 text-paper' : ''}
            `}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
