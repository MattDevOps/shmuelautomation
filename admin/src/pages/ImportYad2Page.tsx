import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createProperty, importFromYad2 } from '../api/properties'
import {
  EMPTY_PROPERTY,
  type PropertyCreate,
  type Yad2ImportPreview,
} from '../api/types'
import PropertyForm from '../components/PropertyForm'

function previewToDraft(p: Yad2ImportPreview): PropertyCreate {
  return {
    ...EMPTY_PROPERTY,
    type: 'sale',
    price: p.price ?? '',
    rooms: p.rooms,
    size_sqm: p.size_sqm,
    floor: p.floor,
    address: p.address,
    neighborhood: p.neighborhood,
    description: [p.title, p.description].filter(Boolean).join('\n\n') || null,
    yad2_url: p.url,
  }
}

export default function ImportYad2Page() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [fetching, setFetching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<Yad2ImportPreview | null>(null)
  const [draft, setDraft] = useState<PropertyCreate | null>(null)

  async function handleFetch(e: FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    setFetching(true)
    try {
      const p = await importFromYad2(url)
      setPreview(p)
      setDraft(previewToDraft(p))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.')
      setPreview(null)
      setDraft(null)
    } finally {
      setFetching(false)
    }
  }

  async function save(payload: PropertyCreate): Promise<void> {
    await createProperty(payload)
    navigate('/')
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Import from Yad2</h1>
          <p className="page-subhead">
            Paste a Yad2 listing URL — we&rsquo;ll save the link to the
            property and try to pre-fill fields from the page. Yad2 blocks
            most automated reads, so usually you&rsquo;ll need to type the
            details in manually.
          </p>
        </div>
      </header>

      <form
        onSubmit={(e) => void handleFetch(e)}
        className="import-form"
        aria-label="Import a Yad2 listing"
      >
        <label className="field">
          <span className="label-text">Yad2 URL</span>
          <input
            type="url"
            required
            placeholder="https://www.yad2.co.il/realestate/item/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <button type="submit" className="btn-primary" disabled={fetching}>
          {fetching ? 'Fetching…' : 'Fetch'}
        </button>
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {preview?.warnings.length ? (
        <div role="status" className="warnings">
          <span className="warnings-heading">Some details couldn&rsquo;t be extracted</span>
          <ul>
            {preview.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {preview && preview.image_urls.length > 0 && (
        <section className="yad2-images" aria-labelledby="yad2-photos-heading">
          <h2 id="yad2-photos-heading">Photos found on the listing</h2>
          <p className="muted">
            You&rsquo;ll re-upload these to the property after saving — for now
            they&rsquo;re just shown for reference.
          </p>
          <ul className="photo-grid">
            {preview.image_urls.map((src, i) => (
              <li key={src} className="photo-tile">
                <div className="photo-tile-image">
                  <img src={src} alt={`Yad2 listing photo ${i + 1}`} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {draft && (
        <>
          <hr className="section-divider" />
          <header className="page-header">
            <div>
              <h2>Review and save</h2>
              <p className="page-subhead">
                Pre-filled from Yad2. Edit anything that needs correcting.
              </p>
            </div>
          </header>
          <PropertyForm
            initial={draft}
            submitLabel="Create property"
            onSubmit={save}
            onCancel={() => navigate('/')}
          />
        </>
      )}
    </section>
  )
}
