import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../lib/api'
import { useAuth } from './AuthContext.jsx'
import { useSocket } from './SocketContext.jsx'
import { useToast } from './ToastContext.jsx'

const NotificationContext = createContext(null)

const LABELS = {
  friend_request: (n) => `${n.sender?.username || 'Someone'} sent you a friend request`,
  message: (n) => `New message from ${n.sender?.username || 'someone'}`,
  group_invite: (n) => `${n.sender?.username || 'Someone'} added you to a group`,
  file: (n) => `${n.sender?.username || 'Someone'} shared a file with you`,
  voice: (n) => `${n.sender?.username || 'Someone'} sent a voice message`,
  system: (n) => n.message || 'System notification',
}

export function NotificationProvider({ children }) {
  const { user } = useAuth()
  const { socket, connected } = useSocket()
  const toast = useToast()
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!user) return
    setLoading(true)
    try {
      const res = await api.get('/notifications/', { params: { limit: 30 } })
      setNotifications(res.data.notifications || [])
      setUnreadCount(res.data.unread ?? 0)
    } catch (err) {
      console.error('Failed to load notifications:', extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    load()
  }, [load])

  // Real-time: the backend emits 'notification' to the user's own room
  // (see socket_events/presence_events.py's join_room on connect) whenever
  // NotificationService.create_notification() fires — friend requests, new
  // messages, group invites. No separate join needed; the room already
  // exists once the socket authenticates.
  useEffect(() => {
    if (!socket || !connected) return
    const onNotification = (data) => {
      setNotifications((prev) => [data, ...prev])
      setUnreadCount((prev) => prev + 1)
      toast.info(LABELS[data.notification_type]?.(data) || 'New notification')
    }
    socket.on('notification', onNotification)
    return () => socket.off('notification', onNotification)
  }, [socket, connected, toast])

  const markAsRead = useCallback(async (id) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    setUnreadCount((prev) => Math.max(0, prev - 1))
    try {
      await api.post(`/notifications/${id}/read`)
    } catch (err) {
      console.error('Failed to mark notification read:', extractErrorMessage(err))
    }
  }, [])

  const markAllAsRead = useCallback(async () => {
    const hadUnread = notifications.some((n) => !n.is_read)
    if (!hadUnread) return
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setUnreadCount(0)
    try {
      await api.post('/notifications/read-all')
    } catch (err) {
      console.error('Failed to mark all notifications read:', extractErrorMessage(err))
    }
  }, [notifications])

  const dismiss = useCallback(async (id) => {
    const wasUnread = notifications.find((n) => n.id === id && !n.is_read)
    setNotifications((prev) => prev.filter((n) => n.id !== id))
    if (wasUnread) setUnreadCount((prev) => Math.max(0, prev - 1))
    try {
      await api.delete(`/notifications/${id}`)
    } catch (err) {
      console.error('Failed to delete notification:', extractErrorMessage(err))
    }
  }, [notifications])

  const value = { notifications, unreadCount, loading, markAsRead, markAllAsRead, dismiss, label: (n) => LABELS[n.notification_type]?.(n) || n.message || 'Notification' }

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
}

export function useNotifications() {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotifications must be used within NotificationProvider')
  return ctx
}
