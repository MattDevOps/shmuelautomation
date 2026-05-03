import { useEffect, useState, type FormEvent } from 'react'
import { listSegments } from '../api/contacts'
import type { ContactCreate } from '../api/types'
import SegmentInput from './SegmentInput'

interface Props {
  initial: ContactCreate
  submitLabel: string
  onSubmit: (payload: ContactCreate) => Promise<void>
  onCancel: () => void
}

function nullable(v: string): string | null {
  return v.trim() === '' ? null : v
}

export default function ContactForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: Props) {
  const [form, setForm] = useState<ContactCreate>(initial)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    listSegments()
      .then((s) => {
        if (!cancelled) setSuggestions(s)
      })
      .catch(() => {
        // suggestions are nice-to-have; silent failure is fine
      })
    return () => {
      cancelled = true
    }
  }, [])

  function set<K extends keyof ContactCreate>(
    key: K,
    value: ContactCreate[K],
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
      await onSubmit(form)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="property-form">
      <div className="grid">
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

        <label className="field">
          <span className="label-text">Phone</span>
          <input
            type="tel"
            value={form.phone ?? ''}
            onChange={(e) => set('phone', nullable(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Email</span>
          <input
            type="email"
            value={form.email ?? ''}
            onChange={(e) => set('email', nullable(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Language</span>
          <select
            value={form.language ?? ''}
            onChange={(e) =>
              set('language', e.target.value === '' ? null : e.target.value)
            }
          >
            <option value="">—</option>
            <option value="he">Hebrew</option>
            <option value="en">English</option>
            <option value="ru">Russian</option>
            <option value="fr">French</option>
            <option value="other">Other</option>
          </select>
        </label>

        <label className="field">
          <span className="label-text">Source</span>
          <input
            type="text"
            value={form.source ?? ''}
            onChange={(e) => set('source', nullable(e.target.value))}
            placeholder="e.g. manual, referral, website"
          />
        </label>

        <label className="field full">
          <span className="label-text">Segments</span>
          <SegmentInput
            value={form.segments}
            onChange={(next) => set('segments', next)}
            suggestions={suggestions}
          />
        </label>

        <label className="field full">
          <span className="label-text">Notes</span>
          <textarea
            rows={4}
            dir="auto"
            value={form.notes ?? ''}
            onChange={(e) => set('notes', nullable(e.target.value))}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button type="button" className="btn" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}
