import { useEffect, useState } from 'react'
import { listPhotos } from '../api/cloud'
import type { CloudPhoto, Property } from '../api/types'

interface Props {
  property: Property
  onClose: () => void
}

export default function PhotoLightbox({ property, onClose }: Props) {
  const [photos, setPhotos] = useState<CloudPhoto[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listPhotos(property.id)
      .then((data) => {
        if (cancelled) return
        setPhotos(data)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [property.id])

  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const label = property.neighborhood ?? property.address ?? property.id

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="lightbox-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal modal-wide">
        <header className="modal-header">
          <div>
            <h2 id="lightbox-title">Photos</h2>
            <p className="muted" dir="auto">
              {label}
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
        <div className="lightbox-body">
          {error && <p className="error">{error}</p>}
          {!error && photos === null && <p className="muted">Loading…</p>}
          {!error && photos !== null && photos.length === 0 && (
            <p className="muted">No photos yet for this property.</p>
          )}
          {photos && photos.length > 0 && (
            <div className="lightbox-grid">
              {photos.map((p) => {
                const src = p.thumbnail_url ?? p.web_view_url
                if (!src) return null
                const href = p.web_view_url ?? src
                return (
                  <a
                    key={p.id}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="lightbox-cell"
                    title={p.file_name}
                  >
                    <img src={src} alt={p.file_name} loading="lazy" />
                  </a>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
