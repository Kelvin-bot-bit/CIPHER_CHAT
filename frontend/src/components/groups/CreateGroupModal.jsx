import { useState } from 'react'
import Modal from '../common/Modal.jsx'
import Spinner from '../common/Spinner.jsx'

export default function CreateGroupModal({ open, onClose, friends, onCreate }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPrivate, setIsPrivate] = useState(true)
  const [memberIds, setMemberIds] = useState([])
  const [submitting, setSubmitting] = useState(false)

  const toggleMember = (id) => {
    setMemberIds((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]))
  }

  const reset = () => {
    setName('')
    setDescription('')
    setIsPrivate(true)
    setMemberIds([])
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setSubmitting(true)
    try {
      await onCreate({ group_name: name.trim(), description: description.trim(), is_private: isPrivate, member_ids: memberIds })
      reset()
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New group">
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Group name</span>
          <input
            autoFocus
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50"
            placeholder="Design team"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Description (optional)</span>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface-alt px-3 py-2 text-sm text-paper placeholder:text-muted focus:border-signal/50"
            placeholder="What's this group for?"
          />
        </label>

        <label className="flex items-center justify-between rounded-lg bg-surface-alt px-3 py-2.5">
          <span className="text-sm text-paper">Private group</span>
          <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} className="h-4 w-4 accent-signal" />
        </label>

        {friends.length > 0 && (
          <div>
            <span className="mb-1.5 block text-xs font-medium text-muted">Add friends</span>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-line p-1.5">
              {friends.map((f) => (
                <label key={f.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-paper hover:bg-surface-alt">
                  <input
                    type="checkbox"
                    checked={memberIds.includes(f.id)}
                    onChange={() => toggleMember(f.id)}
                    className="h-4 w-4 accent-signal"
                  />
                  {f.full_name || f.username}
                </label>
              ))}
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !name.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-4 py-2.5 text-sm font-semibold text-ink hover:brightness-95 disabled:opacity-60"
        >
          {submitting && <Spinner size={14} />}
          Create group
        </button>
      </form>
    </Modal>
  )
}
