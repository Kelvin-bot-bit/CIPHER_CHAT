import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useToast } from '../../context/ToastContext.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'
import CreateGroupModal from './CreateGroupModal.jsx'

export default function GroupsPanel({ friends, onOpenChat }) {
  const toast = useToast()
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/groups/my-groups')
      setGroups(res.data.groups || [])
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load groups'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const createGroup = async (payload) => {
    try {
      await api.post('/groups/', payload)
      toast.success('Group created')
      load()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not create group'))
      throw err
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
        <p className="text-sm font-medium text-paper">Your groups</p>
        <button
          onClick={() => setModalOpen(true)}
          className="rounded-md bg-signal-dim px-2.5 py-1 text-xs font-medium text-signal hover:brightness-110"
        >
          + New group
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : groups.length === 0 ? (
          <p className="px-2 py-8 text-center text-sm text-muted">No groups yet. Create one to chat with several people at once.</p>
        ) : (
          <ul className="space-y-1">
            {groups.map((g) => (
              <li key={g.id}>
                <button
                  onClick={() => onOpenChat({ id: g.id, type: 'group', name: g.group_name })}
                  className="flex w-full items-center gap-3 rounded-xl p-2 text-left hover:bg-surface-alt"
                >
                  <Avatar name={g.group_name} src={g.group_picture} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-paper">{g.group_name}</p>
                    <p className="truncate text-xs text-muted">
                      {g.member_count} member{g.member_count === 1 ? '' : 's'}
                      {g.is_private ? ' · Private' : ''}
                    </p>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <CreateGroupModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        friends={friends}
        onCreate={createGroup}
      />
    </div>
  )
}
