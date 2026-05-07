import { useEffect, useState } from 'react'
import {
  deleteSubscriber,
  listSubscribers,
  type NewsletterSubscriber,
  type SubscriberListResponse,
} from '../api/newsletter'

function fmt(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IL', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function statusOf(s: NewsletterSubscriber): 'confirmed' | 'pending' | 'unsubscribed' {
  if (s.unsubscribed_at) return 'unsubscribed'
  if (s.confirmed_at) return 'confirmed'
  return 'pending'
}

export default function NewsletterPage() {
  const [data, setData] = useState<SubscriberListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const reload = (): void => setReloadTick((t) => t + 1)

  useEffect(() => {
    let cancelled = false
    listSubscribers()
      .then((d) => {
        if (cancelled) return
        setData(d)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setData({
          items: [],
          stats: { total: 0, confirmed: 0, pending: 0, unsubscribed: 0 },
        })
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [reloadTick])

  async function handleDelete(s: NewsletterSubscriber): Promise<void> {
    if (!confirm(`Delete ${s.email}? This is permanent.`)) return
    await deleteSubscriber(s.id)
    reload()
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Newsletter</h1>
          <p className="page-subhead">
            Anyone who signed up on the website to hear about new listings.
            They get an email when there are at least 3 new properties matching
            their interest since the last one we sent them.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn"
            onClick={reload}
          >
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="error">
          Could not load subscribers: {error}
        </p>
      )}

      {data === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : (
        <>
          <div className="system-grid">
            <StatCard label="Confirmed" value={data.stats.confirmed} />
            <StatCard label="Pending" value={data.stats.pending} />
            <StatCard label="Unsubscribed" value={data.stats.unsubscribed} />
            <StatCard label="Total" value={data.stats.total} />
          </div>

          {data.items.length === 0 ? (
            <div className="callout" style={{ marginTop: 'var(--space-xl)' }}>
              <p className="callout-display">
                No newsletter signups yet. Add the{' '}
                <code>[classic_newsletter]</code> shortcode to a page on
                the website to start collecting them.
              </p>
            </div>
          ) : (
            <div className="table-scroll" style={{ marginTop: 'var(--space-xl)' }}>
              <table className="properties-table">
                <thead>
                  <tr>
                    <th scope="col">Email</th>
                    <th scope="col">Wants</th>
                    <th scope="col">Language</th>
                    <th scope="col">Status</th>
                    <th scope="col">Joined</th>
                    <th scope="col">Last digest</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((s) => (
                    <tr key={s.id}>
                      <td>{s.email}</td>
                      <td className="cell-type">{s.type_filter}</td>
                      <td>{s.language}</td>
                      <td>
                        <span
                          className="cell-type"
                          data-newsletter-status={statusOf(s)}
                        >
                          {statusOf(s)}
                        </span>
                      </td>
                      <td>{fmt(s.created_at)}</td>
                      <td>{fmt(s.last_digest_at)}</td>
                      <td className="row-actions">
                        <button
                          type="button"
                          onClick={() => void handleDelete(s)}
                          aria-label={`Delete ${s.email}`}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}

function StatCard({
  label,
  value,
}: {
  label: string
  value: number
}): React.ReactElement {
  return (
    <div className="status-card">
      <header>
        <span className="status-card-dot" aria-hidden="true" />
        <strong>{label}</strong>
      </header>
      <div className="status-card-value">{value}</div>
    </div>
  )
}
