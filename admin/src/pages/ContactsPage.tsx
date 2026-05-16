import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  deleteContact,
  exportContactsUrl,
  listContacts,
  listSegments,
} from '../api/contacts'
import type { Contact, ContactListFilters } from '../api/types'

export default function ContactsPage() {
  const [filters, setFilters] = useState<ContactListFilters>({})
  const [rows, setRows] = useState<Contact[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [segments, setSegments] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    listSegments()
      .then((s) => {
        if (!cancelled) setSegments(s)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    listContacts(filters)
      .then((data) => {
        if (cancelled) return
        setRows(data)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setRows([])
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [filters])

  async function remove(c: Contact): Promise<void> {
    if (!confirm(`Delete ${c.name}?`)) return
    await deleteContact(c.id)
    setRows((rs) => rs?.filter((r) => r.id !== c.id) ?? null)
  }

  function toggleSegment(seg: string): void {
    const current = filters.segment ?? []
    const next = current.includes(seg)
      ? current.filter((s) => s !== seg)
      : [...current, seg]
    setFilters({ ...filters, segment: next.length > 0 ? next : undefined })
  }

  const activeSegments = filters.segment ?? []

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Contacts</h1>
          <p className="page-subhead">
            Your address book. Tag people by segment, then export a CSV ready
            for any WhatsApp bulk sender.
          </p>
        </div>
        <div className="header-actions">
          <Link className="btn" to="/contacts/import">
            Import CSV
          </Link>
          <a className="btn" href={exportContactsUrl(activeSegments)}>
            {activeSegments.length > 0
              ? `Export (${activeSegments.join(', ')})`
              : 'Export CSV'}
          </a>
          <Link className="btn btn-primary" to="/contacts/new">
            New contact
          </Link>
        </div>
      </header>

      <div className="filters" role="group" aria-label="Filter contacts">
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span className="label-text">Search</span>
          <input
            type="search"
            value={filters.q ?? ''}
            onChange={(e) =>
              setFilters({ ...filters, q: e.target.value || undefined })
            }
            placeholder="name or phone"
          />
        </label>
      </div>

      {segments.length > 0 && (
        <div
          className="segment-filter"
          role="group"
          aria-label="Filter by segment"
        >
          <span className="label-eyebrow">Segments</span>
          <ul className="segment-tags">
            {segments.map((s) => {
              const active = activeSegments.includes(s)
              return (
                <li key={s}>
                  <button
                    type="button"
                    className={
                      active ? 'segment-tag-button active' : 'segment-tag-button'
                    }
                    onClick={() => toggleSegment(s)}
                    aria-pressed={active}
                    dir="auto"
                  >
                    {s}
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {error && (
        <p role="alert" className="error">
          Could not load contacts: {error}
        </p>
      )}

      {rows === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="callout">
          <p className="callout-display">
            {activeSegments.length > 0 || filters.q
              ? 'No contacts match those filters.'
              : 'No contacts yet — add one to start the address book.'}
          </p>
        </div>
      ) : (
        <div className="table-scroll"><table className="properties-table">
          <caption className="sr-only">
            {rows.length} {rows.length === 1 ? 'contact' : 'contacts'}
          </caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Phone</th>
              <th scope="col">Segments</th>
              <th scope="col">Language</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                <td dir="auto">{c.name}</td>
                <td className="num">
                  {c.phone ?? <span className="dim">—</span>}
                </td>
                <td>
                  <ul className="segment-tags small">
                    {c.segments.map((s) => (
                      <li key={s} className="segment-tag" dir="auto">
                        {s}
                      </li>
                    ))}
                    {c.segments.length === 0 && (
                      <span className="dim">—</span>
                    )}
                  </ul>
                </td>
                <td className="cell-type">
                  {c.language ?? <span className="dim">—</span>}
                </td>
                <td className="row-actions">
                  <Link to={`/contacts/${c.id}`}>Edit</Link>
                  <button
                    type="button"
                    onClick={() => void remove(c)}
                    aria-label={`Delete ${c.name}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </section>
  )
}
