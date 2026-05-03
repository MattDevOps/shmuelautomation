import { useEffect, useState } from 'react'
import { listGroups } from '../api/groups'
import { composePropertyPost } from '../api/queue'
import { PLATFORM_LABELS } from '../api/types'
import type { Group, GroupPlatform, PostCompose } from '../api/types'

interface Props {
  propertyId: string
  propertyLabel: string
  propertyType: 'rent' | 'sale'
  onClose: () => void
  onMarkPosted?: () => Promise<void>
}

type Lang = 'en' | 'he'

export default function ShareModal({
  propertyId,
  propertyLabel,
  propertyType,
  onClose,
  onMarkPosted,
}: Props) {
  const [compose, setCompose] = useState<PostCompose | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [postedTo, setPostedTo] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [lang, setLang] = useState<Lang>('en')
  const [copied, setCopied] = useState(false)
  const [jumpedTo, setJumpedTo] = useState<string | null>(null)
  const [posting, setPosting] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      composePropertyPost(propertyId),
      listGroups({ matchesPropertyType: propertyType }),
    ])
      .then(([c, g]) => {
        if (cancelled) return
        setCompose(c)
        setGroups(g)
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [propertyId, propertyType])

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

  async function copyAndOpen(groupId: string, url: string): Promise<void> {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard might be blocked in some browsers — still open the URL.
    }
    setJumpedTo(groupId)
    setTimeout(() => setJumpedTo(null), 1800)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  function toggleGroupPosted(id: string): void {
    setPostedTo((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
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

  // Group the groups by platform for the checklist rendering
  const byPlatform = groups.reduce<Record<string, Group[]>>((acc, g) => {
    ;(acc[g.platform] ??= []).push(g)
    return acc
  }, {})
  const platformsInOrder: GroupPlatform[] = [
    'whatsapp',
    'whatsapp_status',
    'facebook',
    'janglo',
    'other',
  ]

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
      <div className="modal modal-wide">
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
              rows={8}
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
            </div>

            {groups.length > 0 && (
              <section
                className="share-groups"
                aria-labelledby="groups-heading"
              >
                <h3 id="groups-heading">Post to</h3>
                <p className="muted">
                  Tap <em>copy &amp; open ↗</em> on a group — the post text
                  is copied to your clipboard and the group opens in a new
                  tab. Paste, send, then tick it off.
                </p>
                {platformsInOrder.map((p) => {
                  const list = byPlatform[p]
                  if (!list) return null
                  return (
                    <div key={p} className="share-groups-platform">
                      <span className="label-eyebrow">{PLATFORM_LABELS[p]}</span>
                      <ul>
                        {list.map((g) => (
                          <li key={g.id}>
                            <label>
                              <input
                                type="checkbox"
                                checked={postedTo.has(g.id)}
                                onChange={() => toggleGroupPosted(g.id)}
                              />
                              <span dir="auto">{g.name}</span>
                              {g.target_url && (
                                <button
                                  type="button"
                                  className="share-groups-jump"
                                  onClick={(e) => {
                                    e.preventDefault()
                                    void copyAndOpen(g.id, g.target_url!)
                                  }}
                                  aria-label={`Copy text and open ${g.name}`}
                                >
                                  {jumpedTo === g.id ? 'copied ✓' : 'copy & open ↗'}
                                </button>
                              )}
                            </label>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )
                })}
              </section>
            )}

            {onMarkPosted && (
              <div className="modal-actions modal-actions-final">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => void handleMarkPosted()}
                  disabled={posting}
                >
                  {posting ? 'Marking…' : 'Mark slot as posted'}
                </button>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  )
}
