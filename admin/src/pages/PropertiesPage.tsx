import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  EXPORT_URL,
  bulkDeleteProperties,
  bulkUpdateStatus,
  deleteProperty,
  listPhotoSummaries,
  listProperties,
  updateProperty,
} from '../api/properties'
import type {
  Property,
  PropertyListFilters,
  PropertyPhotoSummary,
  PropertyStatus,
  PropertyType,
} from '../api/types'
import { PROPERTY_STATUSES, PROPERTY_TYPES } from '../api/types'
import PhotoLightbox from '../components/PhotoLightbox'

function fmtPrice(p: Property): string {
  const n = Number(p.price)
  return Number.isFinite(n)
    ? `${p.currency} ${n.toLocaleString()}`
    : `${p.currency} ${p.price}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IL', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function sourceLabel(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '')
    if (host.includes('yad2')) return 'Yad2'
    if (host.includes('madlan')) return 'Madlan'
    if (host.includes('janglo')) return 'Janglo'
    return host
  } catch {
    return 'Source'
  }
}

function hasActiveFilters(f: PropertyListFilters): boolean {
  return Boolean(f.type || f.status || f.neighborhood || f.q || f.min_price || f.max_price)
}

export default function PropertiesPage() {
  const [filters, setFilters] = useState<PropertyListFilters>({})
  const [rows, setRows] = useState<Property[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [photoSummaries, setPhotoSummaries] = useState<
    Map<string, PropertyPhotoSummary>
  >(new Map())
  const [lightboxFor, setLightboxFor] = useState<Property | null>(null)
  const selectAllRef = useRef<HTMLInputElement>(null)

  async function reload(): Promise<void> {
    const data = await listProperties(filters)
    setRows(data)
    setError(null)
  }

  useEffect(() => {
    let cancelled = false
    listProperties(filters)
      .then((data) => {
        if (cancelled) return
        setRows(data)
        setError(null)
        setSelected(new Set())
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

  useEffect(() => {
    let cancelled = false
    listPhotoSummaries()
      .then((summaries) => {
        if (cancelled) return
        setPhotoSummaries(new Map(summaries.map((s) => [s.property_id, s])))
      })
      .catch(() => {
        // Photo summary failures are non-fatal — the page still renders
        // without thumbnails.
      })
    return () => {
      cancelled = true
    }
  }, [rows])

  // Keep the select-all checkbox in indeterminate state when partially selected.
  useEffect(() => {
    if (!selectAllRef.current || !rows) return
    const all = rows.length > 0 && rows.every((r) => selected.has(r.id))
    const some = rows.some((r) => selected.has(r.id))
    selectAllRef.current.checked = all
    selectAllRef.current.indeterminate = some && !all
  }, [rows, selected])

  function toggleRow(id: string): void {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll(): void {
    if (!rows) return
    const allSelected = rows.every((r) => selected.has(r.id))
    setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.id)))
  }

  async function flipStatus(p: Property, status: PropertyStatus): Promise<void> {
    const next = await updateProperty(p.id, { status })
    setRows((rs) => rs?.map((r) => (r.id === p.id ? next : r)) ?? null)
  }

  async function remove(p: Property): Promise<void> {
    if (!confirm(`Delete property in ${p.neighborhood ?? 'unknown'}?`)) return
    await deleteProperty(p.id)
    setRows((rs) => rs?.filter((r) => r.id !== p.id) ?? null)
  }

  async function bulkStatus(status: PropertyStatus): Promise<void> {
    const ids = Array.from(selected)
    if (ids.length === 0) return
    setBulkBusy(true)
    try {
      await bulkUpdateStatus(ids, status)
      setSelected(new Set())
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bulk update failed.')
    } finally {
      setBulkBusy(false)
    }
  }

  async function bulkDelete(): Promise<void> {
    const ids = Array.from(selected)
    if (ids.length === 0) return
    if (
      !confirm(
        `Delete ${ids.length} ${ids.length === 1 ? 'property' : 'properties'}? This cannot be undone.`,
      )
    ) {
      return
    }
    setBulkBusy(true)
    try {
      await bulkDeleteProperties(ids)
      setSelected(new Set())
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bulk delete failed.')
    } finally {
      setBulkBusy(false)
    }
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Properties</h1>
          <p className="page-subhead">
            Every listing in one place — search, sort, and post in a single tap.
          </p>
        </div>
        <div className="header-actions">
          <a className="btn" href={EXPORT_URL}>
            Export to Excel
          </a>
          <Link className="btn btn-primary" to="/new">
            New property
          </Link>
        </div>
      </header>

      <div className="filters" role="group" aria-label="Filter properties">
        <label className="field">
          <span className="label-text">Type</span>
          <select
            value={filters.type ?? ''}
            onChange={(e) =>
              setFilters({
                ...filters,
                type: (e.target.value || undefined) as PropertyType | undefined,
              })
            }
          >
            <option value="">All</option>
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
            value={filters.status ?? ''}
            onChange={(e) =>
              setFilters({
                ...filters,
                status: (e.target.value || undefined) as
                  | PropertyStatus
                  | undefined,
              })
            }
          >
            <option value="">All</option>
            {PROPERTY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="label-text">Neighborhood</span>
          <input
            type="text"
            value={filters.neighborhood ?? ''}
            onChange={(e) =>
              setFilters({
                ...filters,
                neighborhood: e.target.value || undefined,
              })
            }
          />
        </label>
        <label className="field">
          <span className="label-text">Search</span>
          <input
            type="search"
            value={filters.q ?? ''}
            onChange={(e) =>
              setFilters({ ...filters, q: e.target.value || undefined })
            }
            placeholder="address, description…"
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="error">
          Could not load properties: {error}
        </p>
      )}

      {selected.size > 0 && (
        <div
          className="bulk-bar"
          role="region"
          aria-label="Bulk actions for selected properties"
        >
          <span className="bulk-count">
            <strong>{selected.size}</strong>{' '}
            {selected.size === 1 ? 'selected' : 'selected'}
          </span>
          <span className="bulk-divider" aria-hidden="true" />
          <span className="bulk-label">Mark as:</span>
          {PROPERTY_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              className="btn"
              onClick={() => void bulkStatus(s)}
              disabled={bulkBusy}
            >
              {s}
            </button>
          ))}
          <span className="bulk-spacer" />
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => void bulkDelete()}
            disabled={bulkBusy}
          >
            Delete
          </button>
          <button
            type="button"
            className="btn-link"
            onClick={() => setSelected(new Set())}
            disabled={bulkBusy}
          >
            Clear
          </button>
        </div>
      )}

      {rows === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="callout">
          <p className="callout-display">No properties match those filters.</p>
          {hasActiveFilters(filters) && (
            <p>
              <button
                type="button"
                className="link-button"
                onClick={() => setFilters({})}
              >
                Clear filters
              </button>
            </p>
          )}
        </div>
      ) : (
        <div className="table-scroll"><table className="properties-table">
          <caption className="sr-only">
            {rows.length} {rows.length === 1 ? 'property' : 'properties'}
          </caption>
          <thead>
            <tr>
              <th scope="col" className="cell-select">
                <input
                  ref={selectAllRef}
                  type="checkbox"
                  aria-label="Select all properties on this page"
                  onChange={toggleAll}
                />
              </th>
              <th scope="col">Type</th>
              <th scope="col">Status</th>
              <th scope="col">Price</th>
              <th scope="col">Rooms</th>
              <th scope="col">Neighborhood</th>
              <th scope="col">Owner</th>
              <th scope="col">Source</th>
              <th scope="col">Photos</th>
              <th scope="col">Added</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} data-selected={selected.has(p.id) || undefined}>
                <td className="cell-select">
                  <input
                    type="checkbox"
                    checked={selected.has(p.id)}
                    onChange={() => toggleRow(p.id)}
                    aria-label={`Select ${p.neighborhood ?? p.id}`}
                  />
                </td>
                <td className="cell-type">{p.type}</td>
                <td>
                  <select
                    aria-label={`Status for ${p.neighborhood ?? p.id}`}
                    className="status-pill"
                    value={p.status}
                    onChange={(e) =>
                      void flipStatus(p, e.target.value as PropertyStatus)
                    }
                  >
                    {PROPERTY_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="num">{fmtPrice(p)}</td>
                <td className="num">{p.rooms ?? <span className="dim">—</span>}</td>
                <td dir="auto">
                  {p.neighborhood ?? <span className="dim">—</span>}
                </td>
                <td dir="auto">
                  {p.owner_name ?? <span className="dim">—</span>}
                </td>
                <td>
                  {p.yad2_url ? (
                    <a
                      href={p.yad2_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="source-link"
                      title={p.yad2_url}
                    >
                      ↗ {sourceLabel(p.yad2_url)}
                    </a>
                  ) : (
                    <span className="dim">—</span>
                  )}
                </td>
                <td>
                  {(() => {
                    const s = photoSummaries.get(p.id)
                    if (!s) return <span className="dim">—</span>
                    return (
                      <button
                        type="button"
                        className="photo-thumb-btn"
                        onClick={() => setLightboxFor(p)}
                        aria-label={`View ${s.count} photos for ${p.neighborhood ?? p.id}`}
                      >
                        {s.first_thumbnail ? (
                          <img
                            src={s.first_thumbnail}
                            alt=""
                            className="photo-thumb"
                          />
                        ) : (
                          <span className="photo-thumb photo-thumb-placeholder" />
                        )}
                        <span className="photo-count">{s.count}</span>
                      </button>
                    )
                  })()}
                </td>
                <td className="num">{fmtDate(p.created_at)}</td>
                <td className="row-actions">
                  <Link to={`/${p.id}`}>Edit</Link>
                  <button
                    type="button"
                    onClick={() => void remove(p)}
                    aria-label={`Delete ${p.neighborhood ?? p.id}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      {lightboxFor && (
        <PhotoLightbox
          property={lightboxFor}
          onClose={() => setLightboxFor(null)}
        />
      )}
    </section>
  )
}
