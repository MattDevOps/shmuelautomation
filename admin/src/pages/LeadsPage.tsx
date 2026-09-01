import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { approveLead, listLeads, rejectLead, updateLead } from '../api/leads'
import type { Lead, LeadList, LeadStatus } from '../api/types'

const FILTERS: Array<{ key: LeadStatus | 'all'; label: string }> = [
  { key: 'pending', label: 'Needs review' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

const REQUIREMENT_LABELS: Array<[string, string]> = [
  ['deal_type', 'Looking to'],
  ['rooms', 'Rooms'],
  ['neighborhoods', 'Neighbourhoods'],
  ['furnished', 'Furnished'],
  ['parking', 'Parking'],
  ['household', 'Household'],
  ['timing', 'Timing'],
  ['budget', 'Budget'],
  ['other', 'Also wants'],
]

function fmt(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IL', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Render one requirement value. Booleans must read as words — a raw `true`
 *  in the middle of an address-book note is meaningless months later. */
function renderValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}

function RequirementList({ lead }: { lead: Lead }) {
  const req = lead.requirements ?? {}
  const rows = REQUIREMENT_LABELS.filter(
    ([key]) => (req as Record<string, unknown>)[key] !== undefined,
  )
  if (rows.length === 0) {
    return <p className="muted">No specific requirements were stated.</p>
  }
  return (
    <dl className="lead-req">
      {rows.map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>{renderValue((req as Record<string, unknown>)[key])}</dd>
        </div>
      ))}
    </dl>
  )
}

function LeadCard({
  lead,
  onChanged,
}: {
  lead: Lead
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(lead.display_name ?? '')
  const [phone, setPhone] = useState(lead.phone ?? '')

  async function run(fn: () => Promise<unknown>): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="settings-card lead-card">
      <div className="lead-head">
        <div>
          <strong>{lead.display_name ?? lead.phone ?? 'Unknown caller'}</strong>
          <span className={`lead-pill lead-${lead.source}`}>
            {lead.source === 'call' ? 'Phone call' : 'WhatsApp'}
          </span>
          {lead.status !== 'pending' ? (
            <span className={`lead-pill lead-${lead.status}`}>{lead.status}</span>
          ) : null}
        </div>
        <span className="muted">{fmt(lead.created_at)}</span>
      </div>

      {lead.phone ? <p className="muted">+{lead.phone}</p> : null}
      {lead.summary ? <p>{lead.summary}</p> : null}
      <RequirementList lead={lead} />

      {editing ? (
        <div className="lead-edit">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await updateLead(lead.id, {
                  display_name: name || null,
                  phone: phone || null,
                })
                setEditing(false)
              })
            }
          >
            Save
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      {lead.status === 'pending' ? (
        <div className="lead-actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => approveLead(lead.id))}
          >
            Add to contacts
          </button>
          <button type="button" disabled={busy} onClick={() => setEditing((v) => !v)}>
            Fix details
          </button>
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={() => void run(() => rejectLead(lead.id))}
          >
            Discard
          </button>
        </div>
      ) : lead.contact_id ? (
        <p>
          <Link to={`/contacts/${lead.contact_id}`}>View the contact</Link>
        </p>
      ) : null}
    </div>
  )
}

export default function LeadsPage() {
  const [filter, setFilter] = useState<LeadStatus | 'all'>('pending')
  const [data, setData] = useState<LeadList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    listLeads(filter === 'all' ? {} : { status: filter })
      .then((d) => {
        if (cancelled) return
        setData(d)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setData(null)
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [filter, tick])

  return (
    <section>
      <h2>Leads</h2>
      <p className="muted">
        People who messaged or called, with what they asked for. Nothing is added
        to your contacts until you approve it here.
      </p>

      <div className="filter-row">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={filter === f.key ? 'active' : ''}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            {f.key === 'pending' && data ? ` (${data.pending})` : ''}
          </button>
        ))}
      </div>

      {error ? <p className="error">Could not load leads: {error}</p> : null}
      {data === null && error === null ? <p className="muted">Loading…</p> : null}
      {data !== null && data.items.length === 0 ? (
        <p className="muted">
          {filter === 'pending'
            ? 'Nothing waiting for review.'
            : 'Nothing here yet.'}
        </p>
      ) : null}

      {data?.items.map((lead) => (
        <LeadCard key={lead.id} lead={lead} onChanged={() => setTick((t) => t + 1)} />
      ))}
    </section>
  )
}
