import { useEffect, useState, type FormEvent } from 'react'
import {
  createPropertyNote,
  deletePropertyNote,
  listPropertyNotes,
} from '../api/properties'
import type { PropertyNote } from '../api/types'

interface Props {
  propertyId: string
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function NoteTimeline({ propertyId }: Props) {
  const [notes, setNotes] = useState<PropertyNote[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    listPropertyNotes(propertyId)
      .then((rows) => {
        if (!cancelled) setNotes(rows)
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setNotes([])
          setError(e.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [propertyId])

  async function handleAdd(e: FormEvent): Promise<void> {
    e.preventDefault()
    const trimmed = body.trim()
    if (!trimmed) return
    setBusy(true)
    setError(null)
    try {
      const created = await createPropertyNote(propertyId, trimmed)
      setNotes((prev) => (prev ? [created, ...prev] : [created]))
      setBody('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save note.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(noteId: string): Promise<void> {
    if (!confirm('Delete this note?')) return
    try {
      await deletePropertyNote(propertyId, noteId)
      setNotes((prev) => prev?.filter((n) => n.id !== noteId) ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete note.')
    }
  }

  return (
    <section
      className="note-timeline"
      aria-labelledby="note-timeline-heading"
    >
      <h2 id="note-timeline-heading">Timeline</h2>
      <p className="muted">
        A running log for this property. Calls with the landlord, showing
        notes, price moves — anything you'll want to remember next time.
      </p>

      <form
        onSubmit={(e) => void handleAdd(e)}
        className="note-form"
        aria-label="Add a timeline entry"
      >
        <label className="field full">
          <span className="sr-only">New note</span>
          <textarea
            rows={2}
            dir="auto"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="What just happened? — e.g. Called landlord, available end of month"
            maxLength={5000}
          />
        </label>
        <div className="form-actions">
          <button
            type="submit"
            className="btn-primary"
            disabled={busy || body.trim() === ''}
          >
            {busy ? 'Saving…' : 'Add to timeline'}
          </button>
        </div>
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {notes === null ? (
        <p className="muted">Loading…</p>
      ) : notes.length === 0 ? (
        <p className="muted">
          No timeline entries yet. The first one shows up here.
        </p>
      ) : (
        <ol className="note-list">
          {notes.map((n) => (
            <li key={n.id} className="note-row">
              <div className="note-meta">
                <time dateTime={n.created_at}>
                  {formatTimestamp(n.created_at)}
                </time>
                <button
                  type="button"
                  className="btn-link"
                  onClick={() => void handleDelete(n.id)}
                  aria-label="Delete this note"
                >
                  Delete
                </button>
              </div>
              <p className="note-body" dir="auto">
                {n.body}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
