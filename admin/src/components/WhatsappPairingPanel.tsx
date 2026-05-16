import { useEffect, useState } from 'react'
import {
  getWhatsappQr,
  getWhatsappStatus,
  resetWhatsapp,
} from '../api/whatsapp'
import type { WhatsappStatus } from '../api/types'

const STATUS_POLL_MS = 5_000
const QR_POLL_MS = 3_000

export default function WhatsappPairingPanel(): React.ReactElement {
  const [status, setStatus] = useState<WhatsappStatus | null>(null)
  const [qrPng, setQrPng] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)

  // Poll status while the panel is mounted so Shmuel sees connection state
  // change after he scans the QR without having to refresh the page.
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null

    async function tick(): Promise<void> {
      try {
        const s = await getWhatsappStatus()
        if (stopped) return
        setStatus(s)
        setError(null)
      } catch (e) {
        if (stopped) return
        setError(e instanceof Error ? e.message : 'Status check failed')
      }
      if (!stopped) timer = setTimeout(tick, STATUS_POLL_MS)
    }

    void tick()
    return () => {
      stopped = true
      if (timer !== null) clearTimeout(timer)
    }
  }, [])

  // Only poll the QR endpoint when the daemon is configured + reachable but
  // not yet connected. Avoids hammering the QR route in the steady state.
  const needsQr =
    status !== null &&
    status.configured &&
    status.reachable &&
    status.connection_state !== 'connected'

  useEffect(() => {
    if (!needsQr) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null

    async function tick(): Promise<void> {
      try {
        const r = await getWhatsappQr()
        if (stopped) return
        setQrPng(r.qrPng)
      } catch {
        // Swallow — status poll surfaces the real error.
      }
      if (!stopped) timer = setTimeout(tick, QR_POLL_MS)
    }

    void tick()
    return () => {
      stopped = true
      if (timer !== null) clearTimeout(timer)
    }
  }, [needsQr])

  async function handleReset(): Promise<void> {
    if (
      !confirm(
        'Reset the WhatsApp daemon? This wipes its session and forces a re-pairing. ' +
          'Use this only after a ban or when switching phones.',
      )
    )
      return
    setResetting(true)
    try {
      await resetWhatsapp()
      // Force an immediate status refresh by clearing — the poll loop will
      // pick it back up within STATUS_POLL_MS.
      setStatus(null)
      setQrPng(null)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reset failed')
    } finally {
      setResetting(false)
    }
  }

  if (status === null && error === null) {
    return <p className="muted">Loading…</p>
  }

  if (status !== null && !status.configured) {
    return (
      <div className="settings-card">
        <div className="card-title">
          <span className="status-dot" aria-hidden="true" />
          WhatsApp daemon — not configured
        </div>
        <p className="muted">
          Set <code>WHATSAPP_DAEMON_URL</code> and{' '}
          <code>WHATSAPP_DAEMON_TOKEN</code> in the backend environment to
          enable pairing.
        </p>
      </div>
    )
  }

  if (status !== null && !status.reachable) {
    return (
      <div className="settings-card">
        <div className="card-title">
          <span className="status-dot" aria-hidden="true" />
          WhatsApp daemon — unreachable
        </div>
        <p className="muted">
          The daemon is configured but not responding. Check it&rsquo;s
          deployed and the URL/token match on both sides.
        </p>
        {error !== null && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </div>
    )
  }

  const connected = status?.connection_state === 'connected'

  return (
    <div className="settings-card">
      <div className="card-title">
        <span
          className={connected ? 'status-dot connected' : 'status-dot'}
          aria-hidden="true"
        />
        {connected
          ? 'WhatsApp daemon — connected'
          : 'WhatsApp daemon — waiting for pairing'}
      </div>
      <dl className="kv">
        <dt>State</dt>
        <dd>{status?.connection_state ?? 'unknown'}</dd>
        {status?.paired_phone && (
          <>
            <dt>Paired phone</dt>
            <dd>{status.paired_phone}</dd>
          </>
        )}
        {status?.last_connected_at && (
          <>
            <dt>Last connected</dt>
            <dd>{status.last_connected_at}</dd>
          </>
        )}
        {status?.last_disconnect_reason && (
          <>
            <dt>Last disconnect</dt>
            <dd>{status.last_disconnect_reason}</dd>
          </>
        )}
      </dl>

      {needsQr && qrPng !== null && (
        <div className="whatsapp-qr">
          <p className="muted">
            On your phone: WhatsApp → Settings → Linked Devices → Link a
            Device. Scan this code:
          </p>
          <img src={qrPng} alt="WhatsApp pairing QR code" />
        </div>
      )}
      {needsQr && qrPng === null && (
        <p className="muted">Waiting for the daemon to produce a QR…</p>
      )}

      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <button
        type="button"
        className="btn"
        onClick={() => void handleReset()}
        disabled={resetting}
      >
        {resetting ? 'Resetting…' : 'Reset & re-pair'}
      </button>
    </div>
  )
}
