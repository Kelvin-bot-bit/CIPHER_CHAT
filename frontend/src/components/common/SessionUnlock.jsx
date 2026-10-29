import { useState } from 'react'
import { useAuth } from '../../context/AuthContext.jsx'

// Shown whenever the app knows who you are (valid session cookie) but has
// no password in memory to decrypt with — after a refresh, a new tab, or
// the inactivity auto-lock. Re-entering the password here never hits
// /auth/login again; it just re-arms the in-memory value used for
// message send/read calls.
export default function SessionUnlock() {
  const { user, setSessionPassword, logout } = useAuth()
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!password) return
    setSubmitting(true)
    // There is no "verify password" endpoint that doesn't also try to use
    // it — the first real send/fetch call will surface an error via toast
    // if it's wrong, at which point the user can just try unlocking again.
    setSessionPassword(password)
    setSubmitting(false)
    setPassword('')
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-ink px-6 text-center">
      <div className="rounded-full bg-surface-alt p-3 text-amber">
        <LockIcon />
      </div>
      <div>
        <p className="font-display text-lg font-semibold text-paper">Session locked</p>
        <p className="mt-1 max-w-xs text-sm text-muted">
          Signed in as <span className="text-paper">{user?.username}</span>. Enter your password to unlock
          message encryption for this session.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="flex w-full max-w-xs flex-col gap-2">
        <input
          type="password"
          autoFocus
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-signal px-3.5 py-2.5 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
        >
          Unlock
        </button>
      </form>
      <button onClick={logout} className="text-xs text-muted underline-offset-2 hover:text-paper hover:underline">
        Not you? Sign out
      </button>
    </div>
  )
}

function LockIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" strokeLinecap="round" />
    </svg>
  )
}
