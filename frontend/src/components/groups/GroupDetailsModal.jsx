import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Modal from '../common/Modal.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'

export default function GroupDetailsModal({ open, onClose, group, friends, onLeft, onDeleted }) {
  const { user, sessionPassword } = useAuth()
  const toast = useToast()
  const [members, setMembers] = useState([])
  const [groupInfo, setGroupInfo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [addingId, setAddingId] = useState('')

  const load = async () => {
    if (!group) return
    setLoading(true)
    try {
      const res = await api.get(`/groups/${group.id}`, { params: { include_members: true } })
      setGroupInfo(res.data.group)
      const rawMembers = res.data.group?.members || []
      const withUsers = await Promise.all(
        rawMembers.map(async (m) => {
          try {
            const u = await api.get(`/users/${m.user_id}`)
            return { ...m, user: u.data.user }
          } catch {
            return { ...m, user: null }
          }
        }),
      )
      setMembers(withUsers)
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load group members'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, group?.id])

  const myRole = members.find((m) => m.user_id === user?.id)?.role
  const isAdmin = myRole === 'admin'
  const isCreator = groupInfo?.created_by === user?.id

  const addMember = async () => {
    if (!addingId) return
    if (!sessionPassword) {
      toast.error('Unlock your session first — adding a member needs your password to hand off the group key')
      return
    }
    try {
      // Adding a member now requires the acting admin's password: the new
      // member's copy of the group key can only be created by decrypting
      // an existing member's copy (the admin's) and re-wrapping it for the
      // new member's public key — there's no other way to recover the raw
      // group key at this point.
      await api.post(`/groups/${group.id}/members`, {
        user_id: Number(addingId),
        password: sessionPassword,
      })
      setAddingId('')
      load()
      toast.success('Member added')
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not add member'))
    }
  }

  const removeMember = async (userId) => {
    try {
      await api.delete(`/groups/${group.id}/members/${userId}`)
      setMembers((m) => m.filter((x) => x.user_id !== userId))
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not remove member'))
    }
  }

  const promote = async (userId) => {
    try {
      await api.post(`/groups/${group.id}/promote/${userId}`)
      load()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not promote member'))
    }
  }

  const demote = async (userId) => {
    try {
      await api.post(`/groups/${group.id}/demote/${userId}`)
      load()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not demote member'))
    }
  }

  const leave = async () => {
    try {
      await api.post(`/groups/${group.id}/leave`)
      toast.info(`Left ${group.group_name}`)
      onLeft?.()
      onClose()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not leave group'))
    }
  }

  const remove = async () => {
    try {
      await api.delete(`/groups/${group.id}`)
      toast.info(`Deleted ${group.group_name}`)
      onDeleted?.()
      onClose()
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not delete group'))
    }
  }

  const memberIds = new Set(members.map((m) => m.user_id))
  const addableFriends = friends.filter((f) => !memberIds.has(f.id))

  return (
    <Modal open={open} onClose={onClose} title={group?.group_name || 'Group'} wide>
      {loading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-4">
          {isAdmin && addableFriends.length > 0 && (
            <div className="flex gap-2">
              <select
                value={addingId}
                onChange={(e) => setAddingId(e.target.value)}
                className="flex-1 rounded-lg border border-line bg-surface-alt px-2.5 py-2 text-sm text-paper"
              >
                <option value="">Add a friend to this group…</option>
                {addableFriends.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.full_name || f.username}
                  </option>
                ))}
              </select>
              <button
                onClick={addMember}
                disabled={!addingId}
                className="rounded-lg bg-signal-dim px-3 py-2 text-sm font-medium text-signal disabled:opacity-50"
              >
                Add
              </button>
            </div>
          )}

          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {members.map((m) => (
              <li key={m.user_id} className="flex items-center gap-3 rounded-xl p-2 hover:bg-surface-alt">
                <Avatar name={m.user?.full_name || m.user?.username || `User ${m.user_id}`} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-paper">
                    {m.user?.full_name || m.user?.username || `User ${m.user_id}`}
                    {m.user_id === user?.id && ' (you)'}
                  </p>
                  <p className="truncate text-xs capitalize text-muted">{m.role}</p>
                </div>
                {isAdmin && m.user_id !== user?.id && (
                  <>
                    {m.role === 'admin' ? (
                      <button
                        onClick={() => demote(m.user_id)}
                        className="rounded-md px-2 py-1 text-xs font-medium text-muted hover:bg-surface-hi"
                      >
                        Demote
                      </button>
                    ) : (
                      <button
                        onClick={() => promote(m.user_id)}
                        className="rounded-md px-2 py-1 text-xs font-medium text-signal hover:bg-signal-dim"
                      >
                        Promote
                      </button>
                    )}
                    <button
                      onClick={() => removeMember(m.user_id)}
                      aria-label="Remove member"
                      className="rounded-md p-1.5 text-muted hover:bg-danger-dim hover:text-danger"
                    >
                      ✕
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>

          <div className="flex gap-2 border-t border-line pt-3">
            <button
              onClick={leave}
              className="flex-1 rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110"
            >
              Leave group
            </button>
            {isCreator && (
              <button
                onClick={remove}
                className="flex-1 rounded-lg bg-danger-dim px-3 py-2 text-sm font-medium text-danger hover:brightness-110"
              >
                Delete group
              </button>
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}
