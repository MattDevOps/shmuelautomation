import { useEffect, useState, type FormEvent } from 'react'
import {
  createGroup,
  deleteGroup,
  listGroups,
  updateGroup,
} from '../api/groups'
import {
  EMPTY_GROUP,
  GROUP_AUDIENCES,
  GROUP_PLATFORMS,
  PLATFORM_LABELS,
  type Group,
  type GroupAudience,
  type GroupCreate,
  type GroupPlatform,
} from '../api/types'

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [editing, setEditing] = useState<Group | 'new' | null>(null)

  const reload = (): void => setReloadTick((t) => t + 1)

  useEffect(() => {
    let cancelled = false
    listGroups({ activeOnly: false })
      .then((data) => {
        if (cancelled) return
        setGroups(data)
        setError(null)
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setGroups([])
          setError(e.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [reloadTick])

  async function handleToggleActive(g: Group): Promise<void> {
    await updateGroup(g.id, { active: !g.active })
    reload()
  }

  async function handleDelete(g: Group): Promise<void> {
    if (!confirm(`Delete "${g.name}"? This is permanent.`)) return
    await deleteGroup(g.id)
    reload()
  }

  // Group by platform for sectioned rendering
  const byPlatform: Record<GroupPlatform, Group[]> = {
    whatsapp: [],
    whatsapp_status: [],
    facebook: [],
    janglo: [],
    other: [],
  }
  for (const g of groups ?? []) {
    byPlatform[g.platform].push(g)
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Groups</h1>
          <p className="page-subhead">
            The destinations the share modal will offer for each property.
            Tag rentals vs sales so the right ones show up automatically.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={() => setEditing('new')}
          >
            New group
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="error">
          Could not load groups: {error}
        </p>
      )}

      {groups === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : groups.length === 0 ? (
        <div className="callout">
          <p className="callout-display">
            No groups yet — add the first one to start posting destinations.
          </p>
        </div>
      ) : (
        GROUP_PLATFORMS.map((p) =>
          byPlatform[p].length === 0 ? null : (
            <section
              key={p}
              aria-labelledby={`platform-${p}`}
              style={{ marginTop: 'var(--space-xl)' }}
            >
              <h2 id={`platform-${p}`}>{PLATFORM_LABELS[p]}</h2>
              <table className="properties-table">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">For</th>
                    <th scope="col">Link</th>
                    <th scope="col">Active</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {byPlatform[p].map((g) => (
                    <tr key={g.id}>
                      <td dir="auto">{g.name}</td>
                      <td className="cell-type">{g.audience}</td>
                      <td>
                        {g.target_url ? (
                          <a
                            href={g.target_url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            open ↗
                          </a>
                        ) : (
                          <span className="dim">—</span>
                        )}
                      </td>
                      <td>
                        <label className="active-toggle">
                          <input
                            type="checkbox"
                            checked={g.active}
                            onChange={() => void handleToggleActive(g)}
                            aria-label={`Active ${g.name}`}
                          />
                        </label>
                      </td>
                      <td className="row-actions">
                        <button type="button" onClick={() => setEditing(g)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(g)}
                          aria-label={`Delete ${g.name}`}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ),
        )
      )}

      {editing !== null && (
        <GroupModal
          initial={editing === 'new' ? EMPTY_GROUP : groupToCreate(editing)}
          editingId={editing === 'new' ? null : editing.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            reload()
          }}
        />
      )}
    </section>
  )
}

function groupToCreate(g: Group): GroupCreate {
  return {
    platform: g.platform,
    audience: g.audience,
    name: g.name,
    target_url: g.target_url,
    notes: g.notes,
    sort_order: g.sort_order,
    active: g.active,
  }
}

interface ModalProps {
  initial: GroupCreate
  editingId: string | null
  onClose: () => void
  onSaved: () => void
}

function GroupModal({ initial, editingId, onClose, onSaved }: ModalProps): React.ReactElement {
  const [form, setForm] = useState<GroupCreate>(initial)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof GroupCreate>(
    key: K,
    value: GroupCreate[K],
  ): void {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function handleSubmit(e: FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    if (form.name.trim() === '') {
      setError('Name is required.')
      return
    }
    setSubmitting(true)
    try {
      if (editingId === null) {
        await createGroup(form)
      } else {
        await updateGroup(editingId, form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="group-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal">
        <header className="modal-header">
          <h2 id="group-modal-title">
            {editingId === null ? 'New group' : 'Edit group'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="modal-close"
          >
            ×
          </button>
        </header>

        <form onSubmit={(e) => void handleSubmit(e)} className="property-form">
          <div className="grid">
            <label className="field">
              <span className="label-text">Platform</span>
              <select
                value={form.platform}
                onChange={(e) =>
                  set('platform', e.target.value as GroupPlatform)
                }
              >
                {GROUP_PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {PLATFORM_LABELS[p]}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="label-text">For</span>
              <select
                value={form.audience}
                onChange={(e) =>
                  set('audience', e.target.value as GroupAudience)
                }
              >
                {GROUP_AUDIENCES.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>

            <label className="field full">
              <span className="label-text">
                Name<span className="required-mark" aria-hidden="true">*</span>
              </span>
              <input
                type="text"
                dir="auto"
                required
                value={form.name}
                onChange={(e) => set('name', e.target.value)}
              />
            </label>

            <label className="field full">
              <span className="label-text">Link (optional)</span>
              <input
                type="url"
                value={form.target_url ?? ''}
                onChange={(e) =>
                  set('target_url', e.target.value === '' ? null : e.target.value)
                }
                placeholder="https://chat.whatsapp.com/… or Facebook group URL"
              />
            </label>

            <label className="field">
              <span className="label-text">Sort order</span>
              <input
                type="number"
                value={form.sort_order}
                onChange={(e) =>
                  set('sort_order', Number(e.target.value) || 0)
                }
              />
            </label>

            <label className="field">
              <span className="label-text">Active</span>
              <select
                value={form.active ? 'yes' : 'no'}
                onChange={(e) => set('active', e.target.value === 'yes')}
              >
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>

            <label className="field full">
              <span className="label-text">Notes</span>
              <textarea
                rows={3}
                dir="auto"
                value={form.notes ?? ''}
                onChange={(e) =>
                  set('notes', e.target.value === '' ? null : e.target.value)
                }
              />
            </label>
          </div>

          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="btn"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting}
            >
              {submitting ? 'Saving…' : editingId === null ? 'Create' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
