import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useSocket } from '../../context/SocketContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'
import { formatRelative } from '../../utils/time'
import StatusComposerModal from './StatusComposerModal.jsx'
import StatusViewerModal from './StatusViewerModal.jsx'

export default function StatusPanel() {
  const { user } = useAuth()
  const { socket } = useSocket()
  const toast = useToast()
  const [feed, setFeed] = useState([])
  const [loading, setLoading] = useState(true)
  const [composerOpen, setComposerOpen] = useState(false)
  const [viewingEntry, setViewingEntry] = useState(null)

  const load = async () => {
    try {
      const res = await api.get('/status/feed')
      setFeed(res.data.feed || [])
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load status updates'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Real-time: a friend posting refreshes the tray immediately rather
  // than waiting for this tab to be revisited.
  useEffect(() => {
    if (!socket) return
    const onNewStatus = () => load()
    socket.on('new_status', onNewStatus)
    return () => socket.off('new_status', onNewStatus)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [socket])

  const myEntry = feed.find((e) => e.user.id === user?.id)
  const friendEntries = feed.filter((e) => e.user.id !== user?.id)

  // Order by most-recent unseen first, then most-recent seen — matches
  // the usual "what's new" convention for a status tray.
  const sortedFriends = [...friendEntries].sort((a, b) => {
    if (a.has_unseen !== b.has_unseen) return a.has_unseen ? -1 : 1
    return new Date(b.statuses[0]?.created_at) - new Date(a.statuses[0]?.created_at)
  })

  const closeViewerAndRefresh = () => {
    setViewingEntry(null)
    load()
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-3 py-2.5">
        <p className="text-sm font-medium text-paper">Status</p>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : (
          <>
            {/* My status */}
            <button
              onClick={() => (myEntry ? setViewingEntry(myEntry) : setComposerOpen(true))}
              className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left hover:bg-surface-alt"
            >
              <div className="relative shrink-0">
                <Avatar
                  name={user?.full_name || user?.username || '?'}
                  src={user?.profile_picture}
                  size={48}
                  className={myEntry ? 'ring-2 ring-signal ring-offset-2 ring-offset-ink' : ''}
                />
                {!myEntry && (
                  <span className="absolute -bottom-0.5 -right-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-signal text-ink ring-2 ring-ink">
                    <PlusIcon />
                  </span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-paper">My status</p>
                <p className="flex items-center gap-1.5 truncate text-xs text-muted">
                  {myEntry?.statuses[0].media_type === 'video' && <VideoBadge />}
                  {myEntry
                    ? `${myEntry.statuses.length} update${myEntry.statuses.length === 1 ? '' : 's'} · ${formatRelative(myEntry.statuses[0].created_at)}`
                    : 'Tap to post an update'}
                </p>
              </div>
              {myEntry && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setComposerOpen(true)
                  }}
                  aria-label="Add another status"
                  className="shrink-0 rounded-full p-1.5 text-muted hover:bg-surface-hi hover:text-paper"
                >
                  <PlusIcon />
                </button>
              )}
            </button>

            {sortedFriends.length > 0 && (
              <p className="mb-1 mt-4 px-2.5 text-xs font-medium uppercase tracking-wide text-muted">
                Recent updates
              </p>
            )}

            <ul className="space-y-0.5">
              {sortedFriends.map((entry) => (
                <li key={entry.user.id}>
                  <button
                    onClick={() => setViewingEntry(entry)}
                    className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left hover:bg-surface-alt"
                  >
                    <Avatar
                      name={entry.user.full_name || entry.user.username}
                      src={entry.user.profile_picture}
                      size={48}
                      className={entry.has_unseen ? 'ring-2 ring-signal ring-offset-2 ring-offset-ink' : 'ring-2 ring-line ring-offset-2 ring-offset-ink'}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-paper">
                        {entry.user.full_name || entry.user.username}
                      </p>
                      <p className="flex items-center gap-1.5 truncate text-xs text-muted">
                        {entry.statuses[0].media_type === 'video' && <VideoBadge />}
                        {formatRelative(entry.statuses[0].created_at)}
                      </p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>

            {sortedFriends.length === 0 && !myEntry && (
              <p className="px-2.5 py-8 text-center text-sm text-muted">
                No status updates yet. Post one, or check back once a friend shares an update — updates
                disappear after 24 hours.
              </p>
            )}
          </>
        )}
      </div>

      <StatusComposerModal
        open={composerOpen}
        onClose={() => setComposerOpen(false)}
        onPosted={load}
      />

      {viewingEntry && (
        <StatusViewerModal
          entry={viewingEntry}
          isOwn={viewingEntry.user.id === user?.id}
          onClose={closeViewerAndRefresh}
        />
      )}
    </div>
  )
}

function PlusIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  )
}

// Marks a tray row whose latest update is a video.
function VideoBadge() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-label="Video" role="img" className="shrink-0 text-signal">
      <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" />
    </svg>
  )
}
