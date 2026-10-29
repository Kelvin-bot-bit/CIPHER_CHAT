import { useCallback, useEffect, useRef, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useSocket } from '../../context/SocketContext.jsx'
import { useCall } from '../../context/CallContext.jsx'
import { useGroupCall } from '../../context/GroupCallContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'
import FingerprintRibbon from './FingerprintRibbon.jsx'
import MessageBubble from './MessageBubble.jsx'
import CallLogEntry from './CallLogEntry.jsx'
import GroupCallLogEntry from './GroupCallLogEntry.jsx'
import MessageInput from './MessageInput.jsx'
import TypingIndicator from './TypingIndicator.jsx'
import FileShareModal from './FileShareModal.jsx'
import VoiceRecorderModal from './VoiceRecorderModal.jsx'
import { callToEntry, groupCallToEntry, mergeTimeline } from '../../utils/callLog'

// Poll interval used only as a fallback when the socket isn't connected —
// with real-time wired up, this mostly just catches messages sent while
// this tab was backgrounded. See lib/socket.js for the auth mechanism.
const FALLBACK_POLL_MS = 20000
const BASE_BACKOFF_MS = 60000
const MAX_BACKOFF_MS = 5 * 60000

export default function ChatWindow({ chat, onBack, onOpenFiles, onOpenGroupInfo }) {
  const { user, sessionPassword, isLocked, touchActivity, accessToken } = useAuth()
  const { socket, connected, isOnline, getTypingUsers } = useSocket()
  const { startCall, callState } = useCall()
  const { startGroupCall, callState: groupCallState } = useGroupCall()
  const toast = useToast()

  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [sending, setSending] = useState(false)
  const [peerPublicKey, setPeerPublicKey] = useState(null)
  const [peerUserInfo, setPeerUserInfo] = useState(null)
  const [replyingTo, setReplyingTo] = useState(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [userCache, setUserCache] = useState({})
  const [attachmentCache, setAttachmentCache] = useState({})
  const [attachmentErrorIds, setAttachmentErrorIds] = useState(() => new Set())
  const [downloadingId, setDownloadingId] = useState(null)
  const [voiceCache, setVoiceCache] = useState({})
  const [fileShareOpen, setFileShareOpen] = useState(false)
  const [voiceRecorderOpen, setVoiceRecorderOpen] = useState(false)
  const scrollRef = useRef(null)
  const bottomRef = useRef(null)
  const stickToBottom = useRef(true)
  const backoffRef = useRef(0)
  const timeoutRef = useRef(null)
  // How many messages have been loaded from the "oldest" end so far — the
  // offset to pass for the next "load older" page. Distinct from
  // messages.length, which can shift slightly from deduping during
  // background merges (see refreshLatest below).
  const oldestOffsetRef = useRef(0)
  // Set right before prepending older messages, so the scroll-position
  // effect below can keep the same content in view instead of the
  // viewport visually jumping when content is added above it.
  const pendingScrollAdjustRef = useRef(null)

  const PAGE_SIZE = 60

  // Finished calls for this chat (1:1 calls with this person, or this
  // group's calls), as timeline entries. They live in their own tables
  // (they have no encrypted body/signature to be messages) but are merged
  // into the same list so they show up in order. Never lets a failure here
  // break the chat itself.
  const fetchCalls = useCallback(async () => {
    try {
      if (chat.type === 'group') {
        const res = await api.get(`/calls/group/${chat.id}`, { params: { limit: 100 } })
        return (res.data.calls || []).map(groupCallToEntry)
      }
      const res = await api.get(`/calls/history/${chat.id}`, { params: { limit: 100 } })
      return (res.data.calls || []).map(callToEntry)
    } catch (err) {
      console.error('Failed to load call history:', extractErrorMessage(err))
      return []
    }
  }, [chat.id, chat.type])

  const refreshCalls = useCallback(async () => {
    const entries = await fetchCalls()
    if (entries.length) setMessages((prev) => mergeTimeline(prev, entries))
  }, [fetchCalls])

  // New calls arrive live via 'call_logged'; if the socket dropped and came
  // back we may have missed one, so catch up once on reconnect.
  const wasConnectedRef = useRef(connected)
  useEffect(() => {
    if (connected && !wasConnectedRef.current) refreshCalls()
    wasConnectedRef.current = connected
  }, [connected, refreshCalls])

  // Initial load for a newly-opened chat: replaces the whole list with the
  // most recent page (plus the call history).
  const loadInitial = useCallback(async () => {
    if (!sessionPassword) return
    setLoading(true)
    try {
      const [res, callEntries] = await Promise.all([
        api.get(`/messages/chat/${chat.id}`, {
          params: { chat_type: chat.type, limit: PAGE_SIZE, offset: 0, password: sessionPassword },
        }),
        fetchCalls(),
      ])
      const fetched = res.data.messages || []
      setMessages(mergeTimeline(fetched, callEntries))
      // Offset is for the messages API only, so count messages, not calls.
      oldestOffsetRef.current = fetched.length
      setHasMore(fetched.length < (res.data.total ?? fetched.length))
      backoffRef.current = 0
    } catch (err) {
      if (err?.response?.status === 429) {
        backoffRef.current = backoffRef.current
          ? Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
          : BASE_BACKOFF_MS
      }
      console.error('Failed to load messages:', extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [chat.id, chat.type, sessionPassword, fetchCalls])

  // Background refresh (poll / socket trigger): re-fetches only the newest
  // page and merges it in by id, rather than replacing the whole list —
  // replacing would blow away any older pages the user has scrolled up to
  // load. This also means edits/deletes/reactions only refresh live for
  // messages within the newest page; older, already-loaded messages won't
  // pick up a live edit made way back in history until the chat is
  // reopened. A known, deliberate simplification rather than building full
  // cursor-based pagination for this pass.
  const refreshLatest = useCallback(async () => {
    if (!sessionPassword) return
    try {
      const res = await api.get(`/messages/chat/${chat.id}`, {
        params: { chat_type: chat.type, limit: PAGE_SIZE, offset: 0, password: sessionPassword },
      })
      const fresh = res.data.messages || []
      setMessages((prev) => {
        const byId = new Map(prev.map((m) => [m.id, m]))
        fresh.forEach((m) => byId.set(m.id, m))
        return Array.from(byId.values()).sort(
          (a, b) => new Date(a.created_at) - new Date(b.created_at),
        )
      })
      backoffRef.current = 0
    } catch (err) {
      if (err?.response?.status === 429) {
        backoffRef.current = backoffRef.current
          ? Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
          : BASE_BACKOFF_MS
      }
      console.error('Failed to refresh messages:', extractErrorMessage(err))
    }
  }, [chat.id, chat.type, sessionPassword])

  // "Load older" — called when scrolled near the top. Fetches the next
  // page further back and prepends it.
  const loadOlder = useCallback(async () => {
    if (!sessionPassword || loadingOlder || !hasMore) return
    setLoadingOlder(true)
    const el = scrollRef.current
    pendingScrollAdjustRef.current = el ? { prevHeight: el.scrollHeight } : null
    try {
      const res = await api.get(`/messages/chat/${chat.id}`, {
        params: {
          chat_type: chat.type,
          limit: PAGE_SIZE,
          offset: oldestOffsetRef.current,
          password: sessionPassword,
        },
      })
      const older = res.data.messages || []
      if (older.length > 0) {
        setMessages((prev) => mergeTimeline(prev, older))
      }
      oldestOffsetRef.current += older.length
      setHasMore(oldestOffsetRef.current < (res.data.total ?? oldestOffsetRef.current))
    } catch (err) {
      console.error('Failed to load older messages:', extractErrorMessage(err))
      pendingScrollAdjustRef.current = null
    } finally {
      setLoadingOlder(false)
    }
  }, [chat.id, chat.type, sessionPassword, loadingOlder, hasMore])

  // Initial load + fallback polling loop (self-scheduling so it can back
  // off on 429 without a fixed interval fighting it).
  useEffect(() => {
    setMessages([])
    setReplyingTo(null)
    setHasMore(true)
    oldestOffsetRef.current = 0
    backoffRef.current = 0
    loadInitial()

    const scheduleNext = () => {
      const delay = backoffRef.current || FALLBACK_POLL_MS
      timeoutRef.current = setTimeout(async () => {
        // Always poll periodically, even when the socket is connected —
        // 'new_message' is the only event the backend actually broadcasts,
        // so edits/deletes/reactions from other participants only surface
        // via this poll, not instantly.
        await refreshLatest()
        scheduleNext()
      }, delay)
    }
    scheduleNext()

    return () => clearTimeout(timeoutRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.id, chat.type, sessionPassword])

  // Real-time: join this chat's room and refetch on new activity instead
  // of waiting for the next poll tick.
  useEffect(() => {
    if (!socket || !connected || !accessToken) return

    socket.emit('join_chat', { chat_id: chat.id, chat_type: chat.type, token: accessToken })

    const isThisChat = (data) =>
      (chat.type === 'user' && (data.sender_id === chat.id || data.sender_id === user?.id)) ||
      (chat.type === 'group' && data.recipient_id === chat.id)

    // Only 'new_message' was previously emitted by the backend (see
    // socket_events/chat_events.py) — edits/deletes are still HTTP-only
    // with no broadcast, so those still only surface via the fallback
    // poll below. 'message_expired' is the one exception: disappearing
    // messages get an explicit push from the cleanup sweep (see
    // services/cleanup_service.py) specifically so expiry clears
    // instantly for both parties instead of waiting on a poll.
    const onNewMessage = (data) => {
      if (isThisChat(data)) refreshLatest()
    }
    const onMessageExpired = (data) => {
      if (data.chat_type === chat.type && data.chat_id === chat.id) {
        setMessages((prev) => prev.filter((m) => m.id !== data.message_id))
      }
    }

    // A call with this person just ended (sent to both participants).
    const onCallLogged = (log) => {
      if (chat.type !== 'user') return
      if (log.caller_id !== chat.id && log.callee_id !== chat.id) return
      setMessages((prev) => mergeTimeline(prev, [callToEntry(log)]))
    }

    socket.on('new_message', onNewMessage)
    socket.on('message_expired', onMessageExpired)
    socket.on('call_logged', onCallLogged)

    // A group call in this group just ended (sent to every member).
    const onGroupCallLogged = (log) => {
      if (chat.type !== 'group' || log.group_id !== chat.id) return
      setMessages((prev) => mergeTimeline(prev, [groupCallToEntry(log)]))
    }
    socket.on('group_call_logged', onGroupCallLogged)

    return () => {
      socket.emit('leave_chat', { chat_id: chat.id, chat_type: chat.type, token: accessToken })
      socket.off('new_message', onNewMessage)
      socket.off('message_expired', onMessageExpired)
      socket.off('call_logged', onCallLogged)
      socket.off('group_call_logged', onGroupCallLogged)
    }
  }, [socket, connected, accessToken, chat.id, chat.type, user?.id, refreshLatest])

  useEffect(() => {
    if (chat.type !== 'user') {
      setPeerPublicKey(null)
      setPeerUserInfo(null)
      return
    }
    let cancelled = false
    api
      .get(`/users/${chat.id}`)
      .then((res) => {
        if (cancelled) return
        setPeerPublicKey(res.data.user?.public_key || null)
        setPeerUserInfo(res.data.user || null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [chat.id, chat.type])

  // Resolve sender display names for group chats. The chat-history endpoint
  // only returns sender_id, not a username, so group bubbles previously
  // rendered nothing for the sender label — this fills that in via a small
  // id -> user cache, fetching only ids we haven't seen yet.
  useEffect(() => {
    if (chat.type !== 'group') return
    const missing = [...new Set(messages.map((m) => m.sender_id))].filter(
      (id) => id !== user?.id && !userCache[id],
    )
    if (missing.length === 0) return
    let cancelled = false
    Promise.all(
      missing.map((id) =>
        api
          .get(`/users/${id}`)
          .then((res) => [id, res.data.user])
          .catch(() => [id, null]),
      ),
    ).then((pairs) => {
      if (cancelled) return
      setUserCache((prev) => {
        const next = { ...prev }
        pairs.forEach(([id, u]) => {
          if (u) next[id] = u
        })
        return next
      })
    })
    return () => {
      cancelled = true
    }
  }, [messages, chat.type, user?.id, userCache])

  // Resolve file attachments. The chat-history endpoint includes file_url/
  // file_name on the message row directly, but not the File record's id
  // (needed to call /files/download/<id>) or its size/mime type — those
  // only come from GET /files/message/<message_id>. Fetched lazily per
  // message that has a file, cached by message id.
  //
  // Failures are tracked separately (attachmentErrorIds) rather than just
  // left out of the cache — previously a failed fetch silently resolved
  // to null, which meant `missing` found the same message again on every
  // re-render and retried forever with no visible feedback: the card was
  // permanently stuck showing "Loading attachment…", disabled, with no
  // way to know it had actually failed (wrong password, a file shared
  // before the RSA-key-wrapping fix with no key wrapped for you, a
  // network blip, etc.) or to retry it.
  useEffect(() => {
    const missing = messages.filter(
      (m) => m.file_url && !attachmentCache[m.id] && !attachmentErrorIds.has(m.id),
    )
    if (missing.length === 0) return
    let cancelled = false
    Promise.all(
      missing.map((m) =>
        api
          .get(`/files/message/${m.id}`)
          .then((res) => [m.id, res.data.files?.[0] || null, null])
          .catch((err) => [m.id, null, extractErrorMessage(err, 'Could not load this attachment')]),
      ),
    ).then((results) => {
      if (cancelled) return
      setAttachmentCache((prev) => {
        const next = { ...prev }
        results.forEach(([id, file]) => {
          if (file) next[id] = file
        })
        return next
      })
      setAttachmentErrorIds((prev) => {
        const next = new Set(prev)
        results.forEach(([id, file, error]) => {
          if (error && !file) next.add(id)
        })
        return next
      })
    })
    return () => {
      cancelled = true
    }
  }, [messages, attachmentCache, attachmentErrorIds])

  const retryAttachment = (messageId) => {
    setAttachmentErrorIds((prev) => {
      const next = new Set(prev)
      next.delete(messageId)
      return next
    })
  }

  // Resolve voice note metadata (id, duration) for voice messages, same
  // lazy-cache-by-message-id pattern as file attachments above.
  useEffect(() => {
    const missing = messages.filter((m) => m.message_type === 'voice' && !voiceCache[m.id])
    if (missing.length === 0) return
    let cancelled = false
    Promise.all(
      missing.map((m) =>
        api
          .get(`/voice/message/${m.id}`)
          .then((res) => [m.id, res.data.voice_note || null])
          .catch(() => [m.id, null]),
      ),
    ).then((pairs) => {
      if (cancelled) return
      setVoiceCache((prev) => {
        const next = { ...prev }
        pairs.forEach(([id, note]) => {
          if (note) next[id] = note
        })
        return next
      })
    })
    return () => {
      cancelled = true
    }
  }, [messages, voiceCache])

  const handleDownloadFile = async (fileId, fileName) => {
    if (!sessionPassword) {
      toast.error('Unlock your session to download this file')
      return
    }
    setDownloadingId(fileId)
    try {
      const res = await api.get(`/files/download/${fileId}`, {
        params: { password: sessionPassword },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      // A blob-typed response means axios parses even error bodies as a
      // Blob, not JSON — extractErrorMessage would just show "[object
      // Blob]" for those, so unpack the real message out of it first.
      let message = 'Download failed'
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text()
          message = JSON.parse(text).error || message
        } catch {
          // Fall through to the generic message below.
        }
      } else {
        message = extractErrorMessage(err, message)
      }
      toast.error(message)
    } finally {
      setDownloadingId(null)
    }
  }

  useEffect(() => {
    if (pendingScrollAdjustRef.current) {
      // Just prepended older messages — keep the same content in view
      // instead of letting the browser's default "keep scrollTop the
      // same" behavior visually shift everything down.
      const el = scrollRef.current
      const { prevHeight } = pendingScrollAdjustRef.current
      pendingScrollAdjustRef.current = null
      if (el) el.scrollTop = el.scrollHeight - prevHeight
      return
    }
    if (stickToBottom.current) bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (el.scrollTop < 200 && hasMore && !loadingOlder) {
      loadOlder()
    }
  }

  const handleTyping = (isTyping) => {
    if (!socket || !connected || !accessToken) return
    socket.emit(isTyping ? 'typing_start' : 'typing_stop', {
      chat_id: chat.id,
      chat_type: chat.type,
      token: accessToken,
    })
  }

  const handleSend = async (text, expiresIn) => {
    if (!sessionPassword) return
    setSending(true)
    const optimistic = {
      id: `optimistic-${Date.now()}`,
      sender_id: user?.id,
      message: text,
      is_valid_signature: true,
      created_at: new Date().toISOString(),
      message_type: 'text',
      reactions: {},
      expires_at: expiresIn ? new Date(Date.now() + expiresIn * 1000).toISOString() : null,
      optimistic: true,
    }
    setMessages((prev) => [...prev, optimistic])
    stickToBottom.current = true

    try {
      await api.post('/messages/send', {
        recipient_id: chat.id,
        recipient_type: chat.type,
        message: text,
        password: sessionPassword,
        reply_to_message_id: replyingTo?.id,
        expires_in_seconds: expiresIn || undefined,
      })
      setReplyingTo(null)
      // Remove the optimistic placeholder before merging in the real
      // message — refreshLatest merges by id, and the optimistic entry's
      // temp id (`optimistic-...`) never matches the real numeric id the
      // server assigns, so without this it would sit there forever
      // alongside the real one instead of being replaced by it.
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id))
      await refreshLatest()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Message failed to send'))
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id))
    } finally {
      setSending(false)
    }
  }

  const handleEdit = async (messageId, newText) => {
    if (!sessionPassword) return
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, message: newText, is_edited: true } : m)))
    try {
      await api.put(`/messages/${messageId}`, { message: newText, password: sessionPassword })
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not edit message'))
      refreshLatest()
    }
  }

  const handleDelete = async (messageId) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, is_deleted: true } : m)))
    try {
      await api.delete(`/messages/${messageId}`, { data: { delete_for_everyone: true } })
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not delete message'))
      refreshLatest()
    }
  }

  const handleReact = async (messageId, emoji) => {
    try {
      const res = await api.post(`/messages/${messageId}/reaction`, { reaction: emoji })
      const summary = res.data.summary
      if (summary) {
        setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, reactions: summary } : m)))
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not react to message'))
    }
  }

  const disabled = isLocked || !sessionPassword
  const typingNames = getTypingUsers(chat.type, chat.id).filter((n) => n !== user?.username)
  const visibleMessages = searchQuery.trim()
    ? messages.filter((m) => m.message?.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : messages
  const peerOnline = chat.type === 'user' && isOnline(chat.id)

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-ink" onClick={touchActivity}>
      <header className="flex items-center gap-3 border-b border-line px-3 py-2.5 sm:px-4">
        <button
          onClick={onBack}
          aria-label="Back to chat list"
          className="rounded-md p-1 text-muted hover:bg-surface-alt hover:text-paper lg:hidden"
        >
          <BackIcon />
        </button>
        <Avatar name={chat.name} status={chat.type === 'user' ? (peerOnline ? 'online' : 'offline') : undefined} size={38} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-display font-semibold text-paper">{chat.name}</p>
          <p className="truncate text-xs text-muted">
            {chat.type === 'group' ? 'Group chat' : peerOnline ? 'Online' : 'Offline'}
            {!connected && ' · Reconnecting…'}
          </p>
        </div>
        {chat.type === 'user' && (
          <>
            <button
              onClick={() => startCall(peerUserInfo || { id: chat.id, username: chat.username, full_name: chat.name }, 'audio')}
              disabled={!peerUserInfo || callState !== 'idle' || groupCallState !== 'idle'}
              aria-label="Start voice call"
              className="rounded-md p-2 text-muted hover:bg-surface-alt hover:text-paper disabled:opacity-40"
            >
              <PhoneIcon />
            </button>
            <button
              onClick={() => startCall(peerUserInfo || { id: chat.id, username: chat.username, full_name: chat.name }, 'video')}
              disabled={!peerUserInfo || callState !== 'idle' || groupCallState !== 'idle'}
              aria-label="Start video call"
              className="rounded-md p-2 text-muted hover:bg-surface-alt hover:text-paper disabled:opacity-40"
            >
              <VideoIcon />
            </button>
          </>
        )}
        {chat.type === 'group' && (
          <>
            <button
              onClick={() => startGroupCall({ id: chat.id, group_name: chat.name }, 'audio')}
              disabled={callState !== 'idle' || groupCallState !== 'idle'}
              aria-label="Start group voice call"
              className="rounded-md p-2 text-muted hover:bg-surface-alt hover:text-paper disabled:opacity-40"
            >
              <PhoneIcon />
            </button>
            <button
              onClick={() => startGroupCall({ id: chat.id, group_name: chat.name }, 'video')}
              disabled={callState !== 'idle' || groupCallState !== 'idle'}
              aria-label="Start group video call"
              className="rounded-md p-2 text-muted hover:bg-surface-alt hover:text-paper disabled:opacity-40"
            >
              <VideoIcon />
            </button>
          </>
        )}
        <button
          onClick={() => setSearchOpen((s) => !s)}
          aria-label="Search this conversation"
          className={`rounded-md p-2 hover:bg-surface-alt hover:text-paper ${searchOpen ? 'text-signal' : 'text-muted'}`}
        >
          <SearchIcon />
        </button>
        {chat.type === 'group' && (
          <button
            onClick={onOpenGroupInfo}
            aria-label="Group members and settings"
            className="rounded-md p-2 text-muted hover:bg-surface-alt hover:text-paper"
          >
            <InfoIcon />
          </button>
        )}
        <button
          onClick={onOpenFiles}
          aria-label="Your encrypted file vault"
          title="Your encrypted file vault (all uploads, not just this chat)"
          className="rounded-md p-2 text-muted hover:bg-surface-alt hover:text-paper"
        >
          <FilesIcon />
        </button>
      </header>

      {chat.type === 'user' && <FingerprintRibbon peerId={chat.id} publicKeyPem={peerPublicKey} />}

      {searchOpen && (
        <div className="border-b border-line px-3 py-2 sm:px-4">
          <input
            autoFocus
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search messages currently loaded in this chat"
            className="w-full rounded-lg border border-line bg-surface-alt px-3 py-1.5 text-sm text-paper placeholder:text-muted focus:border-signal/50"
          />
          <p className="mt-1 text-[0.7rem] text-muted">
            Only searches the {messages.filter((m) => !m.kind).length} most recently loaded messages — content is encrypted, so full
            history search isn't possible without decrypting everything server-side.
          </p>
        </div>
      )}

      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 space-y-2.5 overflow-y-auto px-3 py-4 sm:px-5">
        {loading && (
          <div className="flex h-full items-center justify-center">
            <Spinner />
          </div>
        )}

        {!loading && loadingOlder && (
          <div className="flex justify-center py-2">
            <Spinner size={16} />
          </div>
        )}

        {!loading && !hasMore && messages.length > 0 && !searchQuery.trim() && (
          <p className="py-2 text-center text-xs text-muted">Start of conversation</p>
        )}

        {!loading &&
          visibleMessages.map((m, i) => {
            if (m.kind === 'call') {
              return <CallLogEntry key={m.id} call={m.call} viewerId={user?.id} createdAt={m.created_at} />
            }
            if (m.kind === 'group_call') {
              const starter = m.call.started_by === user?.id ? user : userCache[m.call.started_by]
              return (
                <GroupCallLogEntry
                  key={m.id}
                  call={m.call}
                  viewerId={user?.id}
                  createdAt={m.created_at}
                  starterName={starter?.full_name || starter?.username}
                />
              )
            }
            const senderUser = userCache[m.sender_id]
            return (
              <MessageBubble
                key={m.id}
                message={m}
                isOwn={m.sender_id === user?.id}
                showSender={chat.type === 'group' && (i === 0 || visibleMessages[i - 1].sender_id !== m.sender_id)}
                senderName={senderUser?.full_name || senderUser?.username || `User ${m.sender_id}`}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onReply={setReplyingTo}
                onReact={handleReact}
                attachment={attachmentCache[m.id]}
                attachmentFailed={attachmentErrorIds.has(m.id)}
                onRetryAttachment={() => retryAttachment(m.id)}
                onDownloadFile={handleDownloadFile}
                downloadingFile={downloadingId != null && attachmentCache[m.id]?.id === downloadingId}
                voiceNote={voiceCache[m.id]}
              />
            )
          })}
        <div ref={bottomRef} />
      </div>

      <TypingIndicator names={typingNames} />

      {disabled && (
        <p className="border-t border-line bg-amber-dim px-4 py-2 text-center text-xs text-amber">
          Unlock your session below to send or decrypt messages.
        </p>
      )}

      <MessageInput
        onSend={handleSend}
        sending={sending}
        disabled={disabled}
        onAttach={() => setFileShareOpen(true)}
        onRecordVoice={() => setVoiceRecorderOpen(true)}
        onTyping={handleTyping}
        replyingTo={replyingTo}
        onCancelReply={() => setReplyingTo(null)}
      />

      <FileShareModal
        open={fileShareOpen}
        onClose={() => setFileShareOpen(false)}
        chat={chat}
        onSent={() => refreshLatest()}
      />
      <VoiceRecorderModal
        open={voiceRecorderOpen}
        onClose={() => setVoiceRecorderOpen(false)}
        chat={chat}
        onSent={() => refreshLatest()}
      />
    </div>
  )
}

function BackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function PhoneIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.4.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.5 21 3 13.5 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1L6.6 10.8Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function VideoIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="m16 10 5.2-3.1a1 1 0 0 1 1.5.9v8.4a1 1 0 0 1-1.5.9L16 14" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" strokeLinecap="round" />
    </svg>
  )
}

function InfoIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
    </svg>
  )
}

function FilesIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 4H4v16h16V11" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 4h6v6M20 4l-9 9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
