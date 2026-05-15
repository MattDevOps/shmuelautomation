import { useEffect, useState } from 'react'
import {
  previewDigestHtml,
  type PreviewOptions,
  type SubscriberPreference,
} from '../api/newsletter'

type Lang = 'en' | 'he'

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * Modal that fetches the rendered digest HTML for a hypothetical
 * subscriber and shows it in an iframe via srcDoc. Lets Shmuel toggle
 * language + rent/sale filter so he can sanity-check what each
 * audience segment sees before a real send fires.
 */
export default function DigestPreviewModal({ open, onClose }: Props): React.ReactElement | null {
  const [language, setLanguage] = useState<Lang>('en')
  const [typeFilter, setTypeFilter] = useState<SubscriberPreference>('both')
  const [html, setHtml] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const opts: PreviewOptions = { language, type_filter: typeFilter, limit: 5 }
    previewDigestHtml(opts)
      .then((text) => {
        if (cancelled) return
        setHtml(text)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, language, typeFilter])

  useEffect(() => {
    if (!open) return
    function onEsc(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Newsletter digest preview"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 32, 28, 0.55)',
        zIndex: 5000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#faf6ef',
          borderRadius: '12px',
          width: 'min(100%, 720px)',
          maxHeight: 'calc(100vh - 48px)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 18px 48px rgba(15, 32, 28, 0.35)',
        }}
      >
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 20px',
            borderBottom: '1px solid #ece4d2',
            background: '#fff',
          }}
        >
          <div>
            <strong style={{ fontFamily: 'Georgia, serif', color: '#17483b' }}>
              Digest preview
            </strong>
            <div style={{ fontSize: '12px', color: '#6c6c6c', marginTop: '2px' }}>
              What a subscriber would see if a send fired now
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            aria-label="Close preview"
          >
            Close
          </button>
        </header>

        <div
          style={{
            display: 'flex',
            gap: '12px',
            padding: '12px 20px',
            borderBottom: '1px solid #ece4d2',
            background: '#fff',
            flexWrap: 'wrap',
          }}
        >
          <Segmented
            label="Language"
            value={language}
            options={[
              { value: 'en', label: 'English' },
              { value: 'he', label: 'עברית' },
            ]}
            onChange={(v) => setLanguage(v as Lang)}
          />
          <Segmented
            label="Wants"
            value={typeFilter}
            options={[
              { value: 'both', label: 'Both' },
              { value: 'rent', label: 'Rent' },
              { value: 'sale', label: 'Sale' },
            ]}
            onChange={(v) => setTypeFilter(v as SubscriberPreference)}
          />
        </div>

        <div style={{ flex: 1, overflow: 'auto', background: '#faf6ef', padding: '16px' }}>
          {error ? (
            <p role="alert" className="error">
              {error}
            </p>
          ) : loading ? (
            <p style={{ textAlign: 'center', color: '#6c6c6c', padding: '40px 0' }}>
              Loading preview…
            </p>
          ) : (
            <iframe
              title="Digest preview"
              srcDoc={html}
              style={{
                width: '100%',
                minHeight: '60vh',
                border: '1px solid #ece4d2',
                borderRadius: '8px',
                background: '#fff',
              }}
              sandbox="allow-same-origin"
            />
          )}
        </div>
      </div>
    </div>
  )
}

interface SegmentedOption {
  value: string
  label: string
}

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: SegmentedOption[]
  onChange: (v: string) => void
}): React.ReactElement {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ fontSize: '12px', color: '#6c6c6c', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </span>
      <div
        role="radiogroup"
        aria-label={label}
        style={{
          display: 'inline-flex',
          border: '1px solid #d8c89c',
          borderRadius: '6px',
          overflow: 'hidden',
        }}
      >
        {options.map((opt) => {
          const active = opt.value === value
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(opt.value)}
              style={{
                padding: '6px 12px',
                background: active ? '#17483b' : 'transparent',
                color: active ? '#fff' : '#17483b',
                border: 0,
                cursor: 'pointer',
                fontSize: '13px',
                fontFamily: 'inherit',
              }}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
