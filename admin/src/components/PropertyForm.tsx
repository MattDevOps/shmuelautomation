import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { findDuplicateProperties } from '../api/properties'
import type { DuplicateMatch, PropertyCreate } from '../api/types'
import {
  BROKER_FEE_STATUSES,
  PROPERTY_STATUSES,
  PROPERTY_TYPES,
} from '../api/types'

interface Props {
  initial: PropertyCreate
  submitLabel: string
  onSubmit: (payload: PropertyCreate) => Promise<void>
  onCancel: () => void
  /** Property being edited; excluded from dupe search so it doesn't match itself. */
  currentId?: string
}

function nullable(v: string): string | null {
  return v.trim() === '' ? null : v
}

function nullableInt(v: string): number | null {
  if (v.trim() === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? Math.trunc(n) : null
}

export default function PropertyForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  currentId,
}: Props) {
  const [form, setForm] = useState<PropertyCreate>(initial)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [duplicates, setDuplicates] = useState<DuplicateMatch[]>([])
  const [dismissedDupes, setDismissedDupes] = useState(false)

  function set<K extends keyof PropertyCreate>(
    key: K,
    value: PropertyCreate[K],
  ): void {
    setForm((f) => ({ ...f, [key]: value }))
  }

  // Debounced duplicate check — fires once both neighborhood + address are
  // filled, refires when either changes. Aborts inflight on rapid edits.
  // Note: when fields go empty we do NOT clear `duplicates` state here
  // (that would be a setState-in-effect cascade); the render-time guard
  // below handles hiding the warning instead.
  const nhTrim = form.neighborhood?.trim() ?? ''
  const addrTrim = form.address?.trim() ?? ''
  useEffect(() => {
    if (!nhTrim || !addrTrim) return
    const ctl = new AbortController()
    const timer = setTimeout(() => {
      findDuplicateProperties(nhTrim, addrTrim, currentId)
        .then((matches) => {
          if (!ctl.signal.aborted) {
            setDuplicates(matches)
            setDismissedDupes(false)
          }
        })
        .catch(() => {
          // Non-blocking warning — silent on failure is fine.
        })
    }, 500)
    return () => {
      ctl.abort()
      clearTimeout(timer)
    }
  }, [nhTrim, addrTrim, currentId])

  const showDupes =
    duplicates.length > 0 && !dismissedDupes && nhTrim !== '' && addrTrim !== ''

  async function handleSubmit(e: FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    if (!form.price || Number(form.price) < 0) {
      setError('Price is required and must be non-negative.')
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
        <label className="field">
          <span className="label-text">Type</span>
          <select
            value={form.type}
            onChange={(e) => set('type', e.target.value as PropertyCreate['type'])}
          >
            {PROPERTY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="label-text">Status</span>
          <select
            value={form.status}
            onChange={(e) =>
              set('status', e.target.value as PropertyCreate['status'])
            }
          >
            {PROPERTY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="label-text">
            Price<span className="required-mark" aria-hidden="true">*</span>
          </span>
          <input
            type="number"
            min="0"
            step="0.01"
            required
            value={form.price}
            onChange={(e) => set('price', e.target.value)}
          />
        </label>

        <label className="field">
          <span className="label-text">Currency</span>
          <input
            type="text"
            maxLength={3}
            value={form.currency}
            onChange={(e) => set('currency', e.target.value.toUpperCase())}
          />
        </label>

        <label className="field">
          <span className="label-text">Rooms</span>
          <input
            type="number"
            min="0"
            step="0.5"
            value={form.rooms ?? ''}
            onChange={(e) => set('rooms', nullable(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Size (sqm)</span>
          <input
            type="number"
            min="0"
            value={form.size_sqm ?? ''}
            onChange={(e) => set('size_sqm', nullableInt(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Floor</span>
          <input
            type="number"
            value={form.floor ?? ''}
            onChange={(e) => set('floor', nullableInt(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Neighborhood</span>
          <input
            type="text"
            dir="auto"
            value={form.neighborhood ?? ''}
            onChange={(e) => set('neighborhood', nullable(e.target.value))}
          />
        </label>

        <label className="field full">
          <span className="label-text">Address</span>
          <input
            type="text"
            dir="auto"
            value={form.address ?? ''}
            onChange={(e) => set('address', nullable(e.target.value))}
          />
        </label>

        {showDupes && (
          <div
            className="field full dupe-warning"
            role="status"
            aria-live="polite"
          >
            <div className="dupe-warning-head">
              <strong>
                {duplicates.length === 1
                  ? 'You already have a property at this address.'
                  : `You already have ${duplicates.length} properties at this address.`}
              </strong>
              <button
                type="button"
                className="btn-link"
                onClick={() => setDismissedDupes(true)}
                aria-label="Dismiss duplicate warning"
              >
                Dismiss
              </button>
            </div>
            <ul className="dupe-list">
              {duplicates.map((d) => (
                <li key={d.id}>
                  <Link to={`/${d.id}`}>
                    {d.neighborhood ?? 'Unknown neighborhood'} —{' '}
                    <span dir="auto">{d.address ?? '(no address)'}</span>
                  </Link>
                  <span className="muted">
                    {' '}
                    · {d.type === 'rent' ? 'for rent' : 'for sale'} ·{' '}
                    {d.status} · {d.price} {d.currency}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <label className="field">
          <span className="label-text">Owner name</span>
          <input
            type="text"
            dir="auto"
            value={form.owner_name ?? ''}
            onChange={(e) => set('owner_name', nullable(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Owner phone</span>
          <input
            type="tel"
            value={form.owner_phone ?? ''}
            onChange={(e) => set('owner_phone', nullable(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="label-text">Broker fee</span>
          <select
            value={form.broker_fee_status}
            onChange={(e) =>
              set(
                'broker_fee_status',
                e.target.value as PropertyCreate['broker_fee_status'],
              )
            }
          >
            {BROKER_FEE_STATUSES.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="label-text">Broker fee amount</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.broker_fee_amount ?? ''}
            onChange={(e) => set('broker_fee_amount', nullable(e.target.value))}
          />
        </label>

        <label className="field full">
          <span className="label-text">Yad2 URL</span>
          <input
            type="url"
            value={form.yad2_url ?? ''}
            onChange={(e) => set('yad2_url', nullable(e.target.value))}
          />
        </label>

        <label className="field full">
          <span className="label-text">Description (public)</span>
          <textarea
            rows={3}
            dir="auto"
            value={form.description ?? ''}
            onChange={(e) => set('description', nullable(e.target.value))}
          />
        </label>

        <label className="field full">
          <span className="label-text">Internal notes</span>
          <textarea
            rows={3}
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
