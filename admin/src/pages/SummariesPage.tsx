import { useEffect, useState } from 'react'
import {
  listSummaries,
  runSummarizeAll,
  sendDailyDigest,
} from '../api/summaries'
import type {
  ConversationSummary,
  ConversationSummaryList,
} from '../api/types'

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

function summaryTitle(s: ConversationSummary): string {
  return s.phone_number ? `+${s.phone_number}` : s.chat_jid
}

export default function SummariesPage() {
  const [data, setData] = useState<ConversationSummaryList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [running, setRunning] = useState(false)
  const [runMessage, setRunMessage] = useState<string | null>(null)
  const [digestSending, setDigestSending] = useState(false)
  const [digestMessage, setDigestMessage] = useState<string | null>(null)

  const reload = (): void => setReloadTick((t) => t + 1)

  useEffect(() => {
    let cancelled = false
    listSummaries({ limit: 50 })
      .then((d) => {
        if (cancelled) return
        setData(d)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setData({ summaries: [], total: 0 })
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [reloadTick])

  async function handleRunNow(): Promise<void> {
    setRunning(true)
    setRunMessage(null)
    try {
      const res = await runSummarizeAll()
      setRunMessage(
        `Done — ${res.summarized} summarized, ${res.skipped} skipped of ${res.attempted} threads.`,
      )
      reload()
    } catch (e: unknown) {
      setRunMessage(e instanceof Error ? e.message : 'Failed to run')
    } finally {
      setRunning(false)
    }
  }

  async function handleSendDigest(): Promise<void> {
    setDigestSending(true)
    setDigestMessage(null)
    try {
      const res = await sendDailyDigest()
      setDigestMessage(
        res.sent ? 'Digest sent.' : `Skipped: ${res.reason ?? 'unknown reason'}`,
      )
    } catch (e: unknown) {
      setDigestMessage(e instanceof Error ? e.message : 'Failed to send digest')
    } finally {
      setDigestSending(false)
    }
  }

  const summaries = data?.summaries ?? []

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Conversation summaries</h1>
          <p className="page-subhead">
            LLM rollups of WhatsApp threads. Each summary covers messages
            since the previous run. Action items surface what Shmuel still
            owes the lead.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn"
            onClick={handleSendDigest}
            disabled={digestSending}
          >
            {digestSending ? 'Sending…' : 'Send daily digest'}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleRunNow}
            disabled={running}
          >
            {running ? 'Running…' : 'Summarize now'}
          </button>
        </div>
      </header>

      {(runMessage || digestMessage) && (
        <div className="callout">
          {runMessage && <p>{runMessage}</p>}
          {digestMessage && <p>{digestMessage}</p>}
        </div>
      )}

      {error && (
        <p role="alert" className="error">
          Could not load summaries: {error}
        </p>
      )}

      {data === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : summaries.length === 0 ? (
        <div className="callout">
          <p className="callout-display">No summaries yet</p>
          <p>
            Click <strong>Summarize now</strong> after the chatbot has seen
            some inbound messages, or wait for the daily cron once it's wired.
          </p>
        </div>
      ) : (
        <ul className="summary-list">
          {summaries.map((s) => (
            <li key={s.id} className="summary-card">
              <header className="summary-card-header">
                <h2>{summaryTitle(s)}</h2>
                <span className="summary-card-meta">
                  {fmt(s.period_start)} → {fmt(s.period_end)} ·{' '}
                  {s.message_count} message{s.message_count === 1 ? '' : 's'}
                </span>
              </header>
              <p className="summary-text">{s.summary}</p>
              {s.action_items.length > 0 && (
                <div className="summary-section">
                  <span className="label-eyebrow">Action items</span>
                  <ul className="summary-action-list">
                    {s.action_items.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}
              {(s.mentioned_amounts.length > 0 ||
                s.mentioned_dates.length > 0) && (
                <div className="summary-pills">
                  {s.mentioned_amounts.map((a, i) => (
                    <span key={`a${i}`} className="summary-pill summary-pill-amount">
                      {a}
                    </span>
                  ))}
                  {s.mentioned_dates.map((d, i) => (
                    <span key={`d${i}`} className="summary-pill summary-pill-date">
                      {d}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
