import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  CONNECT_GOOGLE_URL,
  disconnectCloud,
  getCloudStatus,
} from '../api/cloud'
import { getScheduleConfig, updateScheduleConfig } from '../api/schedule'
import type { CloudConnectionStatus, ScheduleConfig } from '../api/types'
import WhatsappPairingPanel from '../components/WhatsappPairingPanel'

function PostingSchedule() {
  const [cfg, setCfg] = useState<ScheduleConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    getScheduleConfig()
      .then((c) => !cancelled && setCfg(c))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  function set<K extends keyof ScheduleConfig>(
    key: K,
    value: ScheduleConfig[K],
  ): void {
    setCfg((c) => (c ? { ...c, [key]: value } : c))
    setSaved(false)
  }

  async function save(): Promise<void> {
    if (!cfg) return
    setSaving(true)
    setError(null)
    try {
      const next = await updateScheduleConfig(cfg)
      setCfg(next)
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the schedule.')
    } finally {
      setSaving(false)
    }
  }

  if (error && !cfg) {
    return (
      <p role="alert" className="error">
        {error}
      </p>
    )
  }
  if (!cfg) return <p className="muted">Loading…</p>

  return (
    <div className="settings-card">
      <p className="muted">
        Available properties post automatically at these times. Up to{' '}
        <strong>{cfg.posts_per_slot}</strong> per slot, skipping Shabbat.
      </p>
      <div className="schedule-grid">
        <label className="field">
          <span className="label-text">Morning slot</span>
          <input
            type="time"
            value={cfg.morning_slot}
            onChange={(e) => set('morning_slot', e.target.value)}
          />
        </label>
        <label className="field">
          <span className="label-text">Evening slot</span>
          <input
            type="time"
            value={cfg.evening_slot}
            onChange={(e) => set('evening_slot', e.target.value)}
          />
        </label>
        <label className="field">
          <span className="label-text">Posts per slot</span>
          <input
            type="number"
            min={1}
            max={50}
            value={cfg.posts_per_slot}
            onChange={(e) =>
              set('posts_per_slot', Number(e.target.value) || 1)
            }
          />
        </label>
        <label className="field">
          <span className="label-text">Shabbat: pause from (Fri)</span>
          <input
            type="time"
            value={cfg.friday_block_after}
            onChange={(e) => set('friday_block_after', e.target.value)}
          />
        </label>
        <label className="field">
          <span className="label-text">Shabbat: resume (Sat)</span>
          <input
            type="time"
            value={cfg.saturday_resume_at}
            onChange={(e) => set('saturday_resume_at', e.target.value)}
          />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="modal-actions">
        <button
          type="button"
          className="btn-primary"
          onClick={() => void save()}
          disabled={saving}
        >
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save schedule'}
        </button>
      </div>
    </div>
  )
}

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

      <h2>Posting schedule</h2>
      <p className="muted">
        When the queue posts each day, how many properties per slot, and the
        Shabbat pause. Changes apply to newly scheduled posts.
      </p>
      <PostingSchedule />
    </section>
  )
}
