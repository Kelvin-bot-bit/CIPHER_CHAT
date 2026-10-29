import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { extractErrorMessage } from '../lib/api'
import Spinner from '../components/common/Spinner.jsx'
import AuthLayout from '../components/layout/AuthLayout.jsx'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(identifier, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(extractErrorMessage(err, 'Invalid username/email or password'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout ctaLabel="Sign in">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
        <div>
          <h1 className="font-display text-2xl font-semibold text-paper">Welcome back</h1>
          <p className="mt-1 text-sm text-muted">Sign in to continue your encrypted conversations.</p>
        </div>

        {error && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger-dim px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Username or email</span>
            <input
              autoFocus
              required
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              placeholder="jane_doe"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              placeholder="••••••••"
            />
          </label>
        </div>

        <p className="rounded-lg bg-surface-alt/70 px-3 py-2 text-xs leading-relaxed text-muted">
          Your password briefly unlocks your private key on the server for each message — it's kept only in
          this tab's memory, never on disk, and clears automatically after 15 minutes idle.
        </p>

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold text-ink transition hover:brightness-95 disabled:opacity-60"
        >
          {submitting && <Spinner size={15} />}
          Sign in
        </button>

        <p className="text-center text-sm text-muted">
          New here?{' '}
          <Link to="/register" className="font-medium text-signal hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
