import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  EXPORT_URL,
  deleteProperty,
  listProperties,
  updateProperty,
} from '../api/properties'
import type {
  Property,
  PropertyListFilters,
  PropertyStatus,
  PropertyType,
} from '../api/types'
import { PROPERTY_STATUSES, PROPERTY_TYPES } from '../api/types'

function fmtPrice(p: Property): string {
  const n = Number(p.price)
  return Number.isFinite(n)
    ? `${p.currency} ${n.toLocaleString()}`
    : `${p.currency} ${p.price}`
}

function hasActiveFilters(f: PropertyListFilters): boolean {
  return Boolean(f.type || f.status || f.neighborhood || f.q || f.min_price || f.max_price)
}

export default function PropertiesPage() {
  const [filters, setFilters] = useState<PropertyListFilters>({})
  const [rows, setRows] = useState<Property[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listProperties(filters)
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

  async function flipStatus(p: Property, status: PropertyStatus): Promise<void> {
    const next = await updateProperty(p.id, { status })
    setRows((rs) => rs?.map((r) => (r.id === p.id ? next : r)) ?? null)
  }

  async function remove(p: Property): Promise<void> {
    if (!confirm(`Delete property in ${p.neighborhood ?? 'unknown'}?`)) return
    await deleteProperty(p.id)
    setRows((rs) => rs?.filter((r) => r.id !== p.id) ?? null)
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
        <table className="properties-table">
          <caption className="sr-only">
            {rows.length} {rows.length === 1 ? 'property' : 'properties'}
          </caption>
          <thead>
            <tr>
              <th scope="col">Type</th>
              <th scope="col">Status</th>
              <th scope="col">Price</th>
              <th scope="col">Rooms</th>
              <th scope="col">Neighborhood</th>
              <th scope="col">Owner</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
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
        </table>
      )}
    </section>
  )
}
