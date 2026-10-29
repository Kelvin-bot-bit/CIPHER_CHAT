import { useEffect, useState } from 'react'
import { api, extractErrorMessage } from '../../lib/api'
import { useAuth } from '../../context/AuthContext.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import { disablePush, enablePush, getPushStatus, isPushSupported } from '../../lib/push'
import Modal from '../common/Modal.jsx'
import Avatar from '../common/Avatar.jsx'
import Spinner from '../common/Spinner.jsx'

export default function ProfileModal({ open, onClose }) {
  const { user, setUser } = useAuth()
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [fullName, setFullName] = useState('')
  const [bio, setBio] = useState('')
  const [pictureUrl, setPictureUrl] = useState('')
  const [stats, setStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(true)
  const [saving, setSaving] = useState(false)
  const [pushStatus, setPushStatus] = useState(null)
  const [pushBusy, setPushBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setFullName(user?.full_name || '')
    setBio(user?.bio || '')
    setPictureUrl(user?.profile_picture || '')
    setEditing(false)
    setLoadingStats(true)
    api
      .get('/users/stats')
      .then((res) => setStats(res.data.stats || res.data))
      .catch(() => setStats(null))
      .finally(() => setLoadingStats(false))
    getPushStatus().then(setPushStatus)
  }, [open, user])

  const save = async () => {
    setSaving(true)
    try {
      const res = await api.put('/users/profile', {
        full_name: fullName.trim(),
        bio: bio.trim(),
        profile_picture: pictureUrl.trim() || undefined,
      })
      setUser(res.data.user)
      setEditing(false)
      toast.success('Profile updated')
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not update profile'))
    } finally {
      setSaving(false)
    }
  }

  const togglePush = async () => {
    setPushBusy(true)
    try {
      if (pushStatus?.subscribed) {
        await disablePush()
        toast.info('Push notifications turned off')
      } else {
        await enablePush()
        toast.success('Push notifications enabled')
      }
      setPushStatus(await getPushStatus())
    } catch (err) {
      toast.error(err.message || 'Could not update push notification settings')
    } finally {
      setPushBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Your profile">
      <div className="space-y-5">
        <div className="flex items-center gap-3">
          <Avatar name={user?.full_name || user?.username} src={editing ? pictureUrl : user?.profile_picture} size={56} />
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold text-paper">{user?.full_name || user?.username}</p>
            <p className="truncate text-sm text-muted">@{user?.username}</p>
          </div>
        </div>

        {editing ? (
          <div className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-muted">Full name</span>
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-muted">Bio</span>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-muted">Profile picture URL</span>
              <input
                value={pictureUrl}
                onChange={(e) => setPictureUrl(e.target.value)}
                placeholder="https://…"
                className="w-full rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper"
              />
              <span className="mt-1 block text-[0.7rem] text-muted">
                There's no dedicated avatar upload endpoint on the backend (file uploads are encrypted and
                require a password to view, which doesn't work for a public-facing avatar) — paste a direct
                image URL instead.
              </span>
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setEditing(false)}
                className="flex-1 rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110"
              >
                Cancel
              </button>
              <button
                onClick={save}
                disabled={saving}
                className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-signal px-3 py-2 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
              >
                {saving && <Spinner size={14} />}
                Save
              </button>
            </div>
          </div>
        ) : (
          <>
            {user?.bio && <p className="text-sm text-paper/80">{user.bio}</p>}
            <button
              onClick={() => setEditing(true)}
              className="w-full rounded-lg bg-surface-hi px-3 py-2 text-sm font-medium text-paper hover:brightness-110"
            >
              Edit profile
            </button>
          </>
        )}

        <div className="border-t border-line pt-4">
          <p className="mb-2 text-xs font-medium text-muted">Activity</p>
          {loadingStats ? (
            <Spinner size={16} />
          ) : stats ? (
            <div className="grid grid-cols-3 gap-2 text-center">
              <StatBox label="Messages" value={stats.message_count ?? stats.messages_sent ?? '—'} />
              <StatBox label="Friends" value={stats.friend_count ?? stats.friends_count ?? '—'} />
              <StatBox label="Groups" value={stats.group_count ?? stats.groups_count ?? '—'} />
            </div>
          ) : (
            <p className="text-xs text-muted">Stats unavailable right now.</p>
          )}
        </div>

        <div className="border-t border-line pt-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 pr-3">
              <p className="text-sm font-medium text-paper">Push notifications</p>
              <p className="text-xs text-muted">
                {!isPushSupported()
                  ? "Not supported in this browser"
                  : pushStatus?.permission === 'denied'
                    ? 'Blocked — re-enable notifications for this site in your browser settings'
                    : 'Get notified even when this tab is closed'}
              </p>
            </div>
            <button
              onClick={togglePush}
              disabled={pushBusy || !isPushSupported() || pushStatus?.permission === 'denied'}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50
                ${pushStatus?.subscribed ? 'bg-signal-dim text-signal' : 'bg-surface-hi text-paper hover:brightness-110'}`}
            >
              {pushBusy ? <Spinner size={13} /> : pushStatus?.subscribed ? 'On' : 'Off'}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function StatBox({ label, value }) {
  return (
    <div className="rounded-lg bg-surface-alt px-2 py-2.5">
      <p className="font-display text-lg font-semibold text-paper">{value}</p>
      <p className="text-[0.68rem] text-muted">{label}</p>
    </div>
  )
}
