import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'

export default function AdminUsers() {
  const { user: currentUser } = useAuth()
  const toast = useToast()
  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)

  const load = async (p = page, q = search) => {
    setLoading(true)
    try {
      const res = await api.get('/admin/users', { params: { page: p, per_page: 20, search: q || undefined } })
      setUsers(res.data.users || [])
      setPages(res.data.pages || 1)
      setPage(res.data.page || 1)
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not load users'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1, search)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSearch = (e) => {
    e.preventDefault()
    load(1, search)
  }

  const updateUser = async (userId, patch, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setBusyId(userId)
    try {
      const res = await api.put(`/admin/users/${userId}`, patch)
      setUsers((prev) => prev.map((u) => (u.id === userId ? res.data.user : u)))
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not update user'))
    } finally {
      setBusyId(null)
    }
  }

  const deleteUser = async (userId, username) => {
    if (!window.confirm(`Permanently delete @${username}? This cannot be undone.`)) return
    setBusyId(userId)
    try {
      await api.delete(`/admin/users/${userId}`)
      setUsers((prev) => prev.filter((u) => u.id !== userId))
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not delete user'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by username, email, or name"
          className="w-full max-w-sm rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50"
        />
        <button type="submit" className="rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110">
          Search
        </button>
      </form>

      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-alt text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Email</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-line">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={u.full_name || u.username} size={28} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-paper">{u.full_name || u.username}</p>
                        <p className="truncate text-xs text-muted">@{u.username}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-muted">{u.email}</td>
                  <td className="px-3 py-2.5">
                    {u.is_suspended ? (
                      <Badge tone="danger">Suspended</Badge>
                    ) : u.is_active ? (
                      <Badge tone="signal">Active</Badge>
                    ) : (
                      <Badge>Inactive</Badge>
                    )}
                  </td>
                  <td className="px-3 py-2.5">{u.is_admin ? <Badge tone="amber">Admin</Badge> : <Badge>Member</Badge>}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex justify-end gap-1.5">
                      {busyId === u.id ? (
                        <Spinner size={14} />
                      ) : (
                        <>
                          <button
                            onClick={() => updateUser(u.id, { is_suspended: !u.is_suspended })}
                            className="rounded-md bg-surface-hi px-2 py-1 text-xs font-medium text-paper hover:brightness-110"
                          >
                            {u.is_suspended ? 'Unsuspend' : 'Suspend'}
                          </button>
                          {u.id !== currentUser?.id && (
                            <button
                              onClick={() =>
                                updateUser(
                                  u.id,
                                  { is_admin: !u.is_admin },
                                  !u.is_admin ? `Grant admin privileges to @${u.username}?` : null,
                                )
                              }
                              className="rounded-md bg-surface-hi px-2 py-1 text-xs font-medium text-paper hover:brightness-110"
                            >
                              {u.is_admin ? 'Demote' : 'Make admin'}
                            </button>
                          )}
                          {u.id !== currentUser?.id && (
                            <button
                              onClick={() => deleteUser(u.id, u.username)}
                              className="rounded-md p-1.5 text-muted hover:bg-danger-dim hover:text-danger"
                              aria-label={`Delete ${u.username}`}
                            >
                              ✕
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-muted">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => load(page - 1, search)}
            className="rounded-md px-2 py-1 text-muted hover:text-paper disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-muted">
            Page {page} of {pages}
          </span>
          <button
            disabled={page >= pages}
            onClick={() => load(page + 1, search)}
            className="rounded-md px-2 py-1 text-muted hover:text-paper disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

function Badge({ tone, children }) {
  const toneClass =
    tone === 'signal'
      ? 'bg-signal-dim text-signal'
      : tone === 'danger'
        ? 'bg-danger-dim text-danger'
        : tone === 'amber'
          ? 'bg-amber-dim text-amber'
          : 'bg-surface-hi text-muted'
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toneClass}`}>{children}</span>
}
