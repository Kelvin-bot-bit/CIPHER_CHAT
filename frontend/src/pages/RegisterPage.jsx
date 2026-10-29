import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { extractErrorMessage } from '../lib/api'
import { isPasswordValid, validateEmail, validateUsername } from '../utils/validators'
import PasswordStrengthMeter from '../components/auth/PasswordStrengthMeter.jsx'
import Spinner from '../components/common/Spinner.jsx'
import AuthLayout from '../components/layout/AuthLayout.jsx'

export default function RegisterPage() {
  const { register, login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', email: '', password: '', fullName: '' })
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const clientErrors = () => {
    const usernameError = validateUsername(form.username)
    if (usernameError) return usernameError
    if (!validateEmail(form.email)) return 'Enter a valid email address'
    if (!isPasswordValid(form.password)) return 'Password does not meet all requirements yet'
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    const clientError = clientErrors()
    if (clientError) {
      setError(clientError)
      return
    }
    setSubmitting(true)
    try {
      await register(form)
      // Registration doesn't log the user in server-side (no cookies are
      // set by /auth/register), so we chain an explicit login with the
      // same credentials to get both the session cookie and the in-memory
      // password needed for encryption right away.
      await login(form.username, form.password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(extractErrorMessage(err, 'Could not create your account'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout ctaLabel="Create account" scrollable>
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
        <div>
          <h1 className="font-display text-2xl font-semibold text-paper">Create your account</h1>
          <p className="mt-1 text-sm text-muted">
            A fresh RSA key pair is generated for you on sign-up — keep your password safe, it's the only way
            to unlock it.
          </p>
        </div>

        {error && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger-dim px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Username</span>
            <input
              autoFocus
              required
              value={form.username}
              onChange={update('username')}
              className="w-full rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              placeholder="jane_doe"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Full name (optional)</span>
            <input
              value={form.fullName}
              onChange={update('fullName')}
              className="w-full rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              placeholder="Jane Doe"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Email</span>
            <input
              type="email"
              required
              value={form.email}
              onChange={update('email')}
              className="w-full rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              placeholder="jane@example.com"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Password</span>
            <input
              type="password"
              required
              value={form.password}
              onChange={update('password')}
              className="w-full rounded-lg border border-line bg-surface-alt px-3.5 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              placeholder="••••••••"
            />
          </label>
          <PasswordStrengthMeter password={form.password} />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold text-ink transition hover:brightness-95 disabled:opacity-60"
        >
          {submitting && <Spinner size={15} />}
          Create account
        </button>

        <p className="text-center text-sm text-muted">
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-signal hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
