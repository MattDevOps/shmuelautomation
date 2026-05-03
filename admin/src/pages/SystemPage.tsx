import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSystemStatus } from '../api/system'
import type { SystemStatus } from '../api/types'

export default function SystemPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    getSystemStatus()
      .then((s) => {
        if (cancelled) return
        setStatus(s)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setStatus(null)
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [reloadTick])

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>System</h1>
          <p className="page-subhead">
            A glance at how the system is doing. If anything reads red,
            you&rsquo;ve got something to investigate before posting.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn"
            onClick={() => setReloadTick((t) => t + 1)}
          >
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="error">
          Could not reach the backend: {error}
        </p>
      )}

      {status === null ? (
        !error && (
          <div className="callout">
            <p className="callout-display">Loading…</p>
          </div>
        )
      ) : (
        <div className="system-grid">
          <StatusCard
            title="Backend"
            ok={status.db_ok}
            value={status.db_ok ? 'Online' : 'Offline'}
            sub={`environment: ${status.environment}`}
          />
          <StatusCard
            title="Google Drive"
            ok={status.drive_connected}
            value={status.drive_connected ? 'Connected' : 'Not connected'}
            sub={
              status.drive_account_email ?? (
                <Link to="/settings">Connect now</Link>
              )
            }
          />
          <StatusCard
            title="Posts due now"
            ok={status.queue_due_now_count === 0}
            value={status.queue_due_now_count}
            sub={
              status.queue_due_now_count > 0 ? (
                <Link to="/queue">Open queue</Link>
              ) : (
                'All caught up'
              )
            }
            okLabel="caught up"
            warnLabel="action needed"
          />
          <StatusCard
            title="Pending in queue"
            ok={true}
            value={status.queue_pending_count}
            sub={
              <Link to="/queue">Open queue</Link>
            }
          />
          <StatusCard
            title="Available properties"
            ok={true}
            value={status.properties_available}
            sub={`of ${status.properties_total} total`}
          />
          <StatusCard
            title="Contacts"
            ok={true}
            value={status.contacts_count}
            sub={<Link to="/contacts">Open address book</Link>}
          />
          <StatusCard
            title="Active groups"
            ok={true}
            value={status.groups_active}
            sub={<Link to="/groups">Manage groups</Link>}
          />
        </div>
      )}
    </section>
  )
}

interface CardProps {
  title: string
  ok: boolean
  value: string | number
  sub: React.ReactNode
  okLabel?: string
  warnLabel?: string
}

function StatusCard({ title, ok, value, sub }: CardProps): React.ReactElement {
  return (
    <article className="status-card" data-ok={ok}>
      <header>
        <span className="status-card-dot" aria-hidden="true" />
        <span className="label-eyebrow">{title}</span>
      </header>
      <p className="status-card-value">{value}</p>
      <p className="status-card-sub">{sub}</p>
    </article>
  )
}
