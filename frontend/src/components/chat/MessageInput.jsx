import { useRef, useState } from 'react'

const MAX_LEN = 10000

const EXPIRY_OPTIONS = [
  { label: 'Off', seconds: null },
  { label: '5 minutes', seconds: 5 * 60 },
  { label: '1 hour', seconds: 60 * 60 },
  { label: '1 day', seconds: 24 * 60 * 60 },
  { label: '1 week', seconds: 7 * 24 * 60 * 60 },
]

export default function MessageInput({ onSend, onAttach, onRecordVoice, onTyping, sending, disabled, replyingTo, onCancelReply }) {
  const [value, setValue] = useState('')
  const [expiresIn, setExpiresIn] = useState(null)
  const [expiryPickerOpen, setExpiryPickerOpen] = useState(false)
  const textareaRef = useRef(null)
  const typingTimeout = useRef(null)

  const grow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  const handleChange = (e) => {
    setValue(e.target.value)
    grow()
    onTyping?.(true)
    clearTimeout(typingTimeout.current)
    typingTimeout.current = setTimeout(() => onTyping?.(false), 1500)
  }

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || sending || disabled) return
    onSend(trimmed, expiresIn)
    setValue('')
    onTyping?.(false)
    requestAnimationFrame(grow)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const currentOption = EXPIRY_OPTIONS.find((o) => o.seconds === expiresIn) || EXPIRY_OPTIONS[0]

  return (
    <div className="border-t border-line bg-surface">
      {replyingTo && (
        <div className="flex items-center gap-2 border-b border-line bg-surface-alt/60 px-3.5 py-1.5 text-xs">
          <span className="h-3 w-0.5 shrink-0 rounded-full bg-signal" />
          <span className="text-muted">Replying to</span>
          <span className="truncate text-paper/80">{replyingTo.message}</span>
          <button onClick={onCancelReply} aria-label="Cancel reply" className="ml-auto shrink-0 text-muted hover:text-paper">
            ✕
          </button>
        </div>
      )}

      {expiresIn && (
        <div className="flex items-center gap-2 border-b border-line bg-amber-dim/60 px-3.5 py-1.5 text-xs text-amber">
          <TimerIcon size={13} />
          <span>Disappearing messages: {currentOption.label} after sending</span>
          <button
            onClick={() => setExpiresIn(null)}
            className="ml-auto shrink-0 font-medium underline-offset-2 hover:underline"
          >
            Turn off
          </button>
        </div>
      )}

      <div className="relative flex items-end gap-2 px-3 py-2.5 sm:px-4">
        <button
          type="button"
          onClick={onAttach}
          disabled={disabled}
          aria-label="Attach file"
          className="mb-1 shrink-0 rounded-full p-2 text-muted transition-colors hover:bg-surface-alt hover:text-paper disabled:opacity-40"
        >
          <PaperclipIcon />
        </button>

        <button
          type="button"
          onClick={onRecordVoice}
          disabled={disabled}
          aria-label="Record a voice message"
          className="mb-1 shrink-0 rounded-full p-2 text-muted transition-colors hover:bg-surface-alt hover:text-paper disabled:opacity-40"
        >
          <MicIcon />
        </button>

        <button
          type="button"
          onClick={() => setExpiryPickerOpen((o) => !o)}
          disabled={disabled}
          aria-label="Set disappearing message timer"
          className={`mb-1 shrink-0 rounded-full p-2 transition-colors hover:bg-surface-alt disabled:opacity-40
            ${expiresIn ? 'text-amber' : 'text-muted hover:text-paper'}`}
        >
          <TimerIcon />
        </button>

        {expiryPickerOpen && (
          <div className="absolute bottom-12 left-24 z-10 w-44 overflow-hidden rounded-xl border border-line bg-surface-hi shadow-xl">
            {EXPIRY_OPTIONS.map((opt) => (
              <button
                key={opt.label}
                onClick={() => {
                  setExpiresIn(opt.seconds)
                  setExpiryPickerOpen(false)
                }}
                className={`block w-full px-3.5 py-2 text-left text-sm hover:bg-surface-alt
                  ${opt.seconds === expiresIn ? 'text-amber' : 'text-paper'}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          maxLength={MAX_LEN}
          disabled={disabled}
          placeholder={disabled ? 'Unlock your session to send messages' : 'Write a secure message'}
          aria-label="Message"
          className="max-h-40 flex-1 resize-none rounded-xl border border-line bg-surface-alt px-3.5 py-2.5 text-[0.925rem] text-paper placeholder:text-muted focus:border-signal/50 disabled:opacity-50"
        />

        <button
          type="button"
          onClick={submit}
          disabled={!value.trim() || sending || disabled}
          aria-label="Send message"
          className="mb-1 shrink-0 rounded-full bg-signal p-2.5 text-ink transition-transform hover:scale-105 disabled:scale-100 disabled:bg-surface-hi disabled:text-muted"
        >
          <SendIcon />
        </button>
      </div>
    </div>
  )
}

function PaperclipIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 11.5 12.4 20a4.5 4.5 0 1 1-6.4-6.4l8.1-8.1a3 3 0 1 1 4.2 4.2l-8.1 8.1a1.5 1.5 0 1 1-2.1-2.1l7.4-7.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m3 11 18-8-8 18-2.5-7L3 11Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 19v3" strokeLinecap="round" />
    </svg>
  )
}

function TimerIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.5 2.5M9 2h6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
