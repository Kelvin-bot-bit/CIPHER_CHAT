import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { connectSocket } from '../lib/socket'
import { useAuth } from './AuthContext.jsx'

const SocketContext = createContext(null)

export function SocketProvider({ children }) {
  const { accessToken, user } = useAuth()
  const [connected, setConnected] = useState(false)
  const [onlineUserIds, setOnlineUserIds] = useState(() => new Set())
  // Keyed by `${chatType}_${chatId}` -> Set of usernames currently typing.
  const [typingByChat, setTypingByChat] = useState({})
  const socketRef = useRef(null)
  const typingTimers = useRef({})

  useEffect(() => {
    if (!accessToken || !user) {
      socketRef.current?.disconnect()
      socketRef.current = null
      setConnected(false)
      return
    }

    const socket = connectSocket(accessToken)
    socketRef.current = socket

    socket.on('connect', () => setConnected(true))
    socket.on('disconnect', () => setConnected(false))

    socket.on('user_online', (data) => {
      setOnlineUserIds((prev) => new Set(prev).add(data.user_id))
    })
    socket.on('user_offline', (data) => {
      setOnlineUserIds((prev) => {
        const next = new Set(prev)
        next.delete(data.user_id)
        return next
      })
    })
    socket.on('status_updated', (data) => {
      if (data.status === 'offline') {
        setOnlineUserIds((prev) => {
          const next = new Set(prev)
          next.delete(data.user_id)
          return next
        })
      } else {
        setOnlineUserIds((prev) => new Set(prev).add(data.user_id))
      }
    })

    const typingKey = (data) => `${data.chat_type}_${data.chat_id}`

    socket.on('user_typing', (data) => {
      const key = typingKey(data)
      setTypingByChat((prev) => {
        const next = { ...prev, [key]: new Set(prev[key]).add(data.username) }
        return next
      })
      clearTimeout(typingTimers.current[`${key}_${data.username}`])
      typingTimers.current[`${key}_${data.username}`] = setTimeout(() => {
        setTypingByChat((prev) => {
          const set = new Set(prev[key])
          set.delete(data.username)
          return { ...prev, [key]: set }
        })
      }, 4000)
    })

    socket.on('user_stopped_typing', (data) => {
      const key = typingKey(data)
      setTypingByChat((prev) => {
        const set = new Set(prev[key])
        set.delete(data.username)
        return { ...prev, [key]: set }
      })
    })

    return () => {
      socket.disconnect()
      socketRef.current = null
      setConnected(false)
    }
  }, [accessToken, user])

  const value = useMemo(
    () => ({
      socket: socketRef.current,
      connected,
      onlineUserIds,
      typingByChat,
      isOnline: (userId) => onlineUserIds.has(userId),
      getTypingUsers: (chatType, chatId) => Array.from(typingByChat[`${chatType}_${chatId}`] || []),
    }),
    [connected, onlineUserIds, typingByChat],
  )

  return <SocketContext.Provider value={value}>{children}</SocketContext.Provider>
}

export function useSocket() {
  const ctx = useContext(SocketContext)
  if (!ctx) throw new Error('useSocket must be used within SocketProvider')
  return ctx
}
