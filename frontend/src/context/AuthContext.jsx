import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../lib/api'

const AuthContext = createContext(null)

// How long the in-memory decryption password survives without activity.
// This is a deliberate security/UX tradeoff: the password never touches
// disk, but that means every browser refresh — or this timeout — requires
// re-entering it before messages can be sent or decrypted again.
const SESSION_LOCK_MS = 15 * 60 * 1000

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(true)
  // Kept in React state only — never localStorage/sessionStorage — because
  // this backend requires the plaintext password on every message send/read
  // call to unlock the private key server-side (see services/key_management.py).
  // That's a property of the backend as shipped, not something the frontend
  // can avoid; keeping it out of any persistent storage is the one mitigation
  // available at this layer.
  const [sessionPassword, setSessionPasswordState] = useState(null)
  // Raw JWT for Socket.IO's handshake (see lib/socket.js for why this can't
  // come from the httpOnly cookie). Populated from /auth/login's response,
  // and refreshed silently on boot via /auth/refresh so a page reload can
  // reconnect sockets without needing the password again.
  const [accessToken, setAccessToken] = useState(null)
  const lockTimer = useRef(null)

  const armLockTimer = useCallback(() => {
    clearTimeout(lockTimer.current)
    lockTimer.current = setTimeout(() => setSessionPasswordState(null), SESSION_LOCK_MS)
  }, [])

  const setSessionPassword = useCallback(
    (password) => {
      setSessionPasswordState(password)
      if (password) armLockTimer()
    },
    [armLockTimer],
  )

  const touchActivity = useCallback(() => {
    if (sessionPassword) armLockTimer()
  }, [sessionPassword, armLockTimer])

  // Try to restore a session from the httpOnly cookie on load. This can
  // recover `user`, but never `sessionPassword` — that's intentional. It
  // also tries a silent /auth/refresh to recover a socket-usable
  // accessToken without requiring the password.
  useEffect(() => {
    let cancelled = false
    api
      .get('/users/me')
      .then(async (res) => {
        if (cancelled) return
        setUser(res.data.user)
        try {
          const refreshRes = await api.post('/auth/refresh', {})
          if (!cancelled) setAccessToken(refreshRes.data.access_token || null)
        } catch {
          // No usable refresh cookie — fine, socket features just stay
          // off until the next login.
        }
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setBooting(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (identifier, password) => {
    const res = await api.post('/auth/login', { identifier, password })
    setUser(res.data.user)
    setSessionPassword(password)
    setAccessToken(res.data.access_token || null)
    return res.data.user
  }, [setSessionPassword])

  const register = useCallback(async ({ username, email, password, fullName }) => {
    const res = await api.post('/auth/register', {
      username,
      email,
      password,
      full_name: fullName || undefined,
    })
    return res.data
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout', {})
    } catch {
      // Even if the network call fails, clear local state — the user's
      // intent to log out should never be blocked by a request error.
    }
    setUser(null)
    setSessionPassword(null)
    setAccessToken(null)
  }, [setSessionPassword])

  const lock = useCallback(() => setSessionPassword(null), [setSessionPassword])

  const value = {
    user,
    setUser,
    booting,
    sessionPassword,
    setSessionPassword,
    accessToken,
    touchActivity,
    isLocked: Boolean(user) && !sessionPassword,
    login,
    register,
    logout,
    lock,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export { extractErrorMessage }
