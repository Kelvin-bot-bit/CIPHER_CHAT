import axios from 'axios'
import { getCsrfAccessToken, getCsrfRefreshToken } from './csrf'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export const api = axios.create({
  baseURL,
  // We rely entirely on the backend's httpOnly JWT cookies for auth, never
  // on a token stored in JS memory or localStorage — this is what keeps a
  // successful XSS from being able to exfiltrate the session.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

const MUTATING = new Set(['post', 'put', 'patch', 'delete'])

api.interceptors.request.use((config) => {
  if (MUTATING.has((config.method || '').toLowerCase())) {
    const csrf = getCsrfAccessToken()
    if (csrf) config.headers['X-CSRF-TOKEN'] = csrf
  }
  return config
})

// Silent-refresh queue: if a request 401s, try /auth/refresh once, then
// replay any requests that were waiting on it. Refresh itself needs the
// *refresh* CSRF cookie, not the access one.
let refreshPromise = null

function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = api
      .post(
        '/auth/refresh',
        {},
        { headers: { 'X-CSRF-TOKEN': getCsrfRefreshToken() || '' } },
      )
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const { config, response } = error
    const isAuthRoute = config?.url?.includes('/auth/login') || config?.url?.includes('/auth/refresh')

    if (response?.status === 401 && !config._retried && !isAuthRoute) {
      config._retried = true
      try {
        await refreshAccessToken()
        return api(config)
      } catch (refreshError) {
        // Refresh failed too — the caller (AuthContext) treats this as a
        // real logout, it isn't handled here to avoid circular imports.
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  },
)

// Every backend error body looks like { error: "message" }. This normalizes
// axios errors down to a plain string so components never have to guess.
export function extractErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  return error?.response?.data?.error || error?.message || fallback
}
