import { io } from 'socket.io-client'

const SOCKET_PATH = '/socket.io'

/**
 * Connects to the backend's Socket.IO server, authenticating via a raw JWT
 * passed in the connection query string — the same string exposed by
 * `/api/auth/login` and `/api/auth/refresh` (see AuthContext's `accessToken`).
 * The httpOnly cookie used for regular HTTP requests can't be read here;
 * this token is the one legitimate exception to "never expose the JWT to
 * JS", carved out specifically because Socket.IO's handshake requires it.
 */
export function connectSocket(token) {
  if (!token) return null

  const socket = io('/', {
    path: SOCKET_PATH,
    query: { token },
    withCredentials: true,
    autoConnect: true,
    reconnection: true,
    reconnectionAttempts: 5,
    reconnectionDelay: 1000,
  })

  return socket
}
