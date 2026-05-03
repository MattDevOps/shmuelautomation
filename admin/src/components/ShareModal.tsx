import { useEffect, useState } from 'react'
import { composePropertyPost } from '../api/queue'
import type { PostCompose } from '../api/types'

interface Props {
  propertyId: string
  propertyLabel: string
  onClose: () => void
  onMarkPosted?: () => Promise<void>
}

type Lang = 'en' | 'he'

export default function ShareModal({
  propertyId,
  propertyLabel,
  onClose,
  onMarkPosted,
}: Props) {
  const [compose, setCompose] = useState<PostCompose | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lang, setLang] = useState<Lang>('en')
  const [copied, setCopied] = useState(false)
  const [posting, setPosting] = useState(false)

  useEffect(() => {
    let cancelled = false
    composePropertyPost(propertyId)
      .then((c) => {
        if (!cancelled) setCompose(c)
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [propertyId])

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const text = compose ? (lang === 'en' ? compose.text_en : compose.text_he) : ''
  const whatsapp = compose
    ? lang === 'he'
      ? `https://wa.me/?text=${encodeURIComponent(compose.text_he)}`
      : compose.whatsapp_share_url
    : ''

  async function copy(): Promise<void> {
    if (!text) return
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  async function handleMarkPosted(): Promise<void> {
    if (!onMarkPosted) return
    setPosting(true)
    try {
      await onMarkPosted()
      onClose()
    } finally {
      setPosting(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="share-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal">
        <header className="modal-header">
          <div>
            <h2 id="share-title">Share property</h2>
            <p className="muted" dir="auto">
              {propertyLabel}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="modal-close"
          >
            ×
          </button>
        </header>

        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}

        {compose === null && !error ? (
          <p className="muted">Composing…</p>
        ) : compose ? (
          <>
            <div className="lang-toggle" role="group" aria-label="Language">
              <button
                type="button"
                className={lang === 'en' ? 'active' : ''}
                onClick={() => setLang('en')}
              >
                English
              </button>
              <button
                type="button"
                className={lang === 'he' ? 'active' : ''}
                onClick={() => setLang('he')}
              >
                עברית
              </button>
            </div>

            <textarea
              className="share-text"
              dir="auto"
              readOnly
              value={text}
              rows={10}
            />

            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => void copy()}>
                {copied ? 'Copied ✓' : 'Copy text'}
              </button>
              <a
                className="btn"
                href={whatsapp}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open WhatsApp
              </a>
              {compose.facebook_share_url && (
                <a
                  className="btn"
                  href={compose.facebook_share_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Share to Facebook
                </a>
              )}
              {onMarkPosted && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => void handleMarkPosted()}
                  disabled={posting}
                >
                  {posting ? 'Marking…' : 'Mark as posted'}
                </button>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
