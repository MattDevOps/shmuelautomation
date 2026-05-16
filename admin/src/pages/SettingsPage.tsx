import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  CONNECT_GOOGLE_URL,
  disconnectCloud,
  getCloudStatus,
} from '../api/cloud'
import type { CloudConnectionStatus } from '../api/types'
import WhatsappPairingPanel from '../components/WhatsappPairingPanel'

export default function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState<CloudConnectionStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [working, setWorking] = useState(false)

  useEffect(() => {
    let cancelled = false
    getCloudStatus()
      .then((s) => {
        if (!cancelled) setStatus(s)
      })
      .catch((e: Error) => {
        if (!cancelled) setLoadError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const cloudConnected = params.get('cloud_connected')
  const cloudError = params.get('cloud_error')

  function clearFlash(): void {
    const next = new URLSearchParams(params)
    next.delete('cloud_connected')
    next.delete('cloud_error')
    setParams(next, { replace: true })
  }

  async function handleDisconnect(): Promise<void> {
    if (!confirm('Disconnect Google Drive? Existing photos stay in Drive.'))
      return
    setWorking(true)
    try {
      await disconnectCloud()
      setStatus({
        provider: 'google_drive',
        connected: false,
        account_email: null,
        root_folder_name: null,
      })
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Disconnect failed.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="page-subhead">
            Connect the services that hold your property photos and contacts.
          </p>
        </div>
      </header>

      {cloudConnected && (
        <p role="status" className="success">
          <span className="status-dot connected" aria-hidden="true" /> Google Drive
          connected.{' '}
          <button type="button" className="link-button" onClick={clearFlash}>
            Dismiss
          </button>
        </p>
      )}
      {cloudError && (
        <p role="alert" className="error">
          Could not connect Google Drive: {cloudError}.{' '}
          <button type="button" className="link-button" onClick={clearFlash}>
            Dismiss
          </button>
        </p>
      )}

      <h2>Photo storage</h2>
      <p className="muted">
        Property photos are uploaded to a folder in your own Google Drive
        account, organised one folder per property.
      </p>

      {loadError && (
        <p role="alert" className="error">
          {loadError}
        </p>
      )}

      {status === null ? (
        <p className="muted">Loading…</p>
      ) : status.connected ? (
        <div className="settings-card">
          <div className="card-title">
            <span className="status-dot connected" aria-hidden="true" />
            Connected to Google Drive
          </div>
          <dl className="kv">
            <dt>Account</dt>
            <dd>{status.account_email ?? 'unknown'}</dd>
            <dt>Folder</dt>
            <dd>{status.root_folder_name ?? 'Classic Jerusalem Realty'}</dd>
          </dl>
          <button
            type="button"
            className="btn"
            onClick={() => void handleDisconnect()}
            disabled={working}
          >
            {working ? 'Disconnecting…' : 'Disconnect Google Drive'}
          </button>
        </div>
      ) : (
        <div className="settings-card">
          <div className="card-title">
            <span className="status-dot" aria-hidden="true" />
            Google Drive — not connected
          </div>
          <p className="muted">
            We&rsquo;ll create one folder per property under{' '}
            <em>Classic Jerusalem Realty</em> in your Drive. Photos can be
            opened directly in Drive whenever you need them.
          </p>
          <a className="btn-primary" href={CONNECT_GOOGLE_URL}>
            Connect Google Drive
          </a>
        </div>
      )}

      <h2>WhatsApp delivery</h2>
      <p className="muted">
        Posts to WhatsApp groups go through a self-hosted daemon paired with
        your phone. Pair it once by scanning a QR; the session persists across
        daemon restarts.
      </p>
      <WhatsappPairingPanel />
    </section>
  )
}
