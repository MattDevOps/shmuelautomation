import { useEffect, useState } from 'react'
import {
  cancelSlot,
  listQueue,
  markPosted,
  skipSlot,
} from '../api/queue'
import type { PostSlotWithProperty } from '../api/types'
import ShareModal from '../components/ShareModal'

function formatScheduled(iso: string): {
  absolute: string
  relative: string
  isOverdue: boolean
} {
  const when = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  const now = new Date()
  const ms = when.getTime() - now.getTime()
  const minutes = Math.round(ms / 60000)
  const absolute = when.toLocaleString('en-IL', {
    timeZone: 'Asia/Jerusalem',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: 'short',
  })
  let relative: string
  const abs = Math.abs(minutes)
  if (abs < 1) relative = 'now'
  else if (abs < 60) relative = `${abs}m`
  else if (abs < 1440) relative = `${Math.round(abs / 60)}h`
  else relative = `${Math.round(abs / 1440)}d`

  return {
    absolute,
    relative: ms < 0 ? `${relative} ago` : `in ${relative}`,
    isOverdue: ms < 0,
  }
}

function fmtPrice(price: string, type: string): string {
  const n = Number(price)
  const formatted = Number.isFinite(n)
    ? n.toLocaleString('en-IL', { maximumFractionDigits: 0 })
    : price
  return `${type === 'rent' ? '/mo' : ''} ILS ${formatted}`
}

export default function QueuePage() {
  const [rows, setRows] = useState<PostSlotWithProperty[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sharing, setSharing] = useState<PostSlotWithProperty | null>(null)

  const [reloadTick, setReloadTick] = useState(0)
  const reload = (): void => setReloadTick((t) => t + 1)

  useEffect(() => {
    let cancelled = false
    listQueue({ limit: 50 })
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
  }, [reloadTick])

  async function handleSkip(slot: PostSlotWithProperty): Promise<void> {
    if (!confirm(`Skip this slot for ${slot.property_neighborhood ?? 'this property'}?`))
      return
    await skipSlot(slot.id)
    reload()
  }

  async function handleCancel(slot: PostSlotWithProperty): Promise<void> {
    if (
      !confirm(
        `Cancel posting for ${slot.property_neighborhood ?? 'this property'}? It won't be re-queued.`,
      )
    )
      return
    await cancelSlot(slot.id)
    reload()
  }

  async function handleMarkPosted(slot: PostSlotWithProperty): Promise<void> {
    await markPosted(slot.id)
    reload()
  }

  const dueRows = rows?.filter((r) => formatScheduled(r.scheduled_for).isOverdue) ?? []
  const upcomingRows =
    rows?.filter((r) => !formatScheduled(r.scheduled_for).isOverdue) ?? []

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Posting queue</h1>
          <p className="page-subhead">
            Two slots a day at 8 AM and 8 PM. Shabbat off. Tap{' '}
            <em>Compose &amp; share</em> when a slot is due — the post text is
            pre-written, you just send it to your groups.
          </p>
        </div>
      </header>

      {error && (
        <p role="alert" className="error">
          Could not load the queue: {error}
        </p>
      )}

      {rows === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="callout">
          <p className="callout-display">
            Nothing in the queue yet. Add a property and it will be scheduled
            automatically.
          </p>
        </div>
      ) : (
        <>
          {dueRows.length > 0 && (
            <section aria-labelledby="due-heading">
              <h2 id="due-heading">Due now</h2>
              <QueueList
                rows={dueRows}
                onShare={setSharing}
                onSkip={(s) => void handleSkip(s)}
                onCancel={(s) => void handleCancel(s)}
              />
            </section>
          )}
          {upcomingRows.length > 0 && (
            <section
              aria-labelledby="upcoming-heading"
              style={{ marginTop: 'var(--space-2xl)' }}
            >
              <h2 id="upcoming-heading">Upcoming</h2>
              <QueueList
                rows={upcomingRows}
                onShare={setSharing}
                onSkip={(s) => void handleSkip(s)}
                onCancel={(s) => void handleCancel(s)}
              />
            </section>
          )}
        </>
      )}

      {sharing && (
        <ShareModal
          propertyId={sharing.property_id}
          propertyLabel={`${sharing.property_neighborhood ?? 'Property'} · ${fmtPrice(
            sharing.property_price,
            sharing.property_type,
          )}`}
          onClose={() => setSharing(null)}
          onMarkPosted={() => handleMarkPosted(sharing)}
        />
      )}
    </section>
  )
}

interface ListProps {
  rows: PostSlotWithProperty[]
  onShare: (slot: PostSlotWithProperty) => void
  onSkip: (slot: PostSlotWithProperty) => void
  onCancel: (slot: PostSlotWithProperty) => void
}

function QueueList({ rows, onShare, onSkip, onCancel }: ListProps): React.ReactElement {
  return (
    <table className="properties-table">
      <thead>
        <tr>
          <th scope="col">When</th>
          <th scope="col">Type</th>
          <th scope="col">Property</th>
          <th scope="col">Price</th>
          <th scope="col">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((slot) => {
          const when = formatScheduled(slot.scheduled_for)
          return (
            <tr key={slot.id}>
              <td>
                <div>{when.absolute}</div>
                <div className="dim">{when.relative}</div>
              </td>
              <td className="cell-type">{slot.property_type}</td>
              <td dir="auto">
                {slot.property_neighborhood ?? slot.property_address ?? '—'}
              </td>
              <td className="num">
                {fmtPrice(slot.property_price, slot.property_type)}
              </td>
              <td className="row-actions">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => onShare(slot)}
                  aria-label={`Compose and share ${slot.property_neighborhood ?? slot.id}`}
                >
                  Compose &amp; share
                </button>
                <button type="button" onClick={() => onSkip(slot)}>
                  Skip
                </button>
                <button type="button" onClick={() => onCancel(slot)}>
                  Cancel
                </button>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
