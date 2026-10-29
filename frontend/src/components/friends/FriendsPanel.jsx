import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useToast } from '../../context/ToastContext.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'

const TABS = ['Friends', 'Requests', 'Find people', 'Blocked']

export default function FriendsPanel({ onOpenChat, onFriendsChanged }) {
  const toast = useToast()
  const [tab, setTab] = useState('Friends')
  const [friends, setFriends] = useState([])
  const [requests, setRequests] = useState([])
  const [blocked, setBlocked] = useState([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [friendsRes, requestsRes, blockedRes] = await Promise.all([
        api.get('/friends/list'),
        api.get('/friends/requests'),
        api.get('/friends/blocked'),
      ])
      setFriends(friendsRes.data.friends || [])
      setBlocked(blockedRes.data.blocked || blockedRes.data.users || [])

      const incoming = (requestsRes.data.received || requestsRes.data.requests || []).filter(
        (r) => r.status === 'pending',
      )
      const withNames = await Promise.all(
        incoming.map(async (r) => {
          try {
            const u = await api.get(`/users/${r.sender_id}`)
            return { ...r, sender: u.data.user }
          } catch {
            return { ...r, sender: null }
          }
        }),
      )
      setRequests(withNames)
      onFriendsChanged?.(friendsRes.data.friends || [])
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load friends'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const search = async (e) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    try {
      const res = await api.get('/friends/search', { params: { query } })
      setResults(res.data.users || res.data.results || [])
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Search failed'))
    } finally {
      setSearching(false)
    }
  }

  const sendRequest = async (userId) => {
    try {
      await api.post('/friends/request', { user_id: userId })
      toast.success('Friend request sent')
      setResults((r) => r.map((u) => (u.id === userId ? { ...u, requested: true } : u)))
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not send request'))
    }
  }

  const respond = async (requestId, action) => {
    try {
      await api.post(`/friends/request/${requestId}/${action}`)
      setRequests((r) => r.filter((req) => req.id !== requestId))
      if (action === 'accept') {
        toast.success('Friend request accepted')
        loadAll()
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not update request'))
    }
  }

  const removeFriend = async (friendId) => {
    try {
      await api.delete(`/friends/${friendId}`)
      setFriends((f) => f.filter((u) => u.id !== friendId))
      toast.info('Friend removed')
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not remove friend'))
    }
  }

  const blockUser = async (userId) => {
    try {
      await api.post('/friends/block', { user_id: userId })
      setFriends((f) => f.filter((u) => u.id !== userId))
      toast.info('User blocked')
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not block user'))
    }
  }

  const unblockUser = async (userId) => {
    try {
      await api.post('/friends/unblock', { user_id: userId })
      setBlocked((b) => b.filter((u) => u.id !== userId))
      toast.info('User unblocked')
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not unblock user'))
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-line p-2">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors
              ${tab === t ? 'bg-surface-hi text-paper' : 'text-muted hover:text-paper'}`}
          >
            {t}
            {t === 'Requests' && requests.length > 0 && (
              <span className="ml-1 rounded-full bg-signal px-1.5 text-[0.65rem] text-ink">{requests.length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading && tab !== 'Find people' ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : tab === 'Friends' ? (
          friends.length === 0 ? (
            <EmptyState text="No friends yet. Search for people to connect with." />
          ) : (
            <ul className="space-y-1">
              {friends.map((f) => (
                <li key={f.id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-surface-alt">
                  <Avatar name={f.full_name || f.username} src={f.profile_picture} status={f.online_status} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-paper">{f.full_name || f.username}</p>
                    <p className="truncate text-xs text-muted">@{f.username}</p>
                  </div>
                  <button
                    onClick={() => onOpenChat({ id: f.id, type: 'user', name: f.full_name || f.username })}
                    className="rounded-md bg-signal-dim px-2 py-1 text-xs font-medium text-signal hover:brightness-110"
                  >
                    Chat
                  </button>
                  <button
                    onClick={() => removeFriend(f.id)}
                    aria-label={`Remove ${f.username}`}
                    className="rounded-md p-1.5 text-muted hover:bg-danger-dim hover:text-danger"
                  >
                    ✕
                  </button>
                  <button
                    onClick={() => blockUser(f.id)}
                    aria-label={`Block ${f.username}`}
                    className="rounded-md p-1.5 text-muted hover:bg-danger-dim hover:text-danger"
                    title="Block"
                  >
                    <BlockIcon />
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : tab === 'Requests' ? (
          requests.length === 0 ? (
            <EmptyState text="No pending friend requests." />
          ) : (
            <ul className="space-y-1">
              {requests.map((r) => (
                <li key={r.id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-surface-alt">
                  <Avatar name={r.sender?.full_name || r.sender?.username || '?'} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-paper">
                      {r.sender?.full_name || r.sender?.username || 'Unknown user'}
                    </p>
                    {r.message && <p className="truncate text-xs text-muted">“{r.message}”</p>}
                  </div>
                  <button
                    onClick={() => respond(r.id, 'accept')}
                    className="rounded-md bg-signal-dim px-2 py-1 text-xs font-medium text-signal hover:brightness-110"
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => respond(r.id, 'reject')}
                    className="rounded-md p-1.5 text-muted hover:bg-danger-dim hover:text-danger"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : tab === 'Find people' ? (
          <div>
            <form onSubmit={search} className="mb-3 flex gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by username"
                className="flex-1 rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50"
              />
              <button
                type="submit"
                disabled={searching}
                className="rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110 disabled:opacity-60"
              >
                {searching ? <Spinner size={14} /> : 'Search'}
              </button>
            </form>
            {results.length === 0 ? (
              <EmptyState text="Search for a username to send a friend request." />
            ) : (
              <ul className="space-y-1">
                {results.map((u) => (
                  <li key={u.id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-surface-alt">
                    <Avatar name={u.full_name || u.username} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-paper">{u.full_name || u.username}</p>
                      <p className="truncate text-xs text-muted">@{u.username}</p>
                    </div>
                    <button
                      onClick={() => sendRequest(u.id)}
                      disabled={u.requested || u.is_friend || u.has_pending_request}
                      className="rounded-md bg-signal-dim px-2 py-1 text-xs font-medium text-signal hover:brightness-110 disabled:cursor-default disabled:bg-surface-hi disabled:text-muted"
                    >
                      {u.requested || u.has_pending_request ? 'Sent' : u.is_friend ? 'Friends' : 'Add'}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : blocked.length === 0 ? (
          <EmptyState text="No blocked users." />
        ) : (
          <ul className="space-y-1">
            {blocked.map((u) => (
              <li key={u.id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-surface-alt">
                <Avatar name={u.full_name || u.username} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-paper">{u.full_name || u.username}</p>
                  <p className="truncate text-xs text-muted">@{u.username}</p>
                </div>
                <button
                  onClick={() => unblockUser(u.id)}
                  className="rounded-md bg-surface-hi px-2 py-1 text-xs font-medium text-paper hover:brightness-110"
                >
                  Unblock
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function EmptyState({ text }) {
  return <p className="px-2 py-8 text-center text-sm text-muted">{text}</p>
}

function BlockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path d="m5.5 5.5 13 13" strokeLinecap="round" />
    </svg>
  )
}
