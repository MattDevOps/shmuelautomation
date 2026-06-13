import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createProperty, importFromYad2 } from '../api/properties'
import { importPhotosFromUrls } from '../api/cloud'
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
  const [importPhotos, setImportPhotos] = useState(true)
  // Set after a property is created but its photos couldn't be imported, so we
  // can link the user to it instead of navigating away silently.
  const [createdId, setCreatedId] = useState<string | null>(null)

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
    const created = await createProperty(payload)
    const urls = preview?.image_urls ?? []
    if (importPhotos && urls.length > 0) {
      // Pull the Yad2 gallery into Drive. The property already exists, so a
      // photo failure is never fatal — but don't hide it: if nothing imported
      // (e.g. Drive disconnected), keep the user here with a clear message and
      // a link to the property rather than dropping them on an empty gallery.
      try {
        const result = await importPhotosFromUrls(created.id, urls)
        if (result.imported === 0 && result.failed > 0) {
          setCreatedId(created.id)
          setError(
            `Property created, but none of the ${result.failed} photos could be ` +
              `imported (${result.errors[0] ?? 'unknown error'}). Open the ` +
              `property to add them manually.`,
          )
          return
        }
      } catch (err) {
        setCreatedId(created.id)
        setError(
          `Property created, but photo import failed: ` +
            `${err instanceof Error ? err.message : 'unknown error'}. Open the ` +
            `property to add photos manually.`,
        )
        return
      }
    }
    // Go to the property so the freshly imported photos are visible.
    navigate(`/${created.id}`)
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Import from Yad2</h1>
          <p className="page-subhead">
            Paste a Yad2 listing URL — we&rsquo;ll pull the price, size, floor,
            address and the full photo gallery, then pre-fill the form below.
            Review, adjust anything, and save. Occasionally Yad2&rsquo;s bot
            check blocks a read; if that happens, just fill the form in manually.
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

      {createdId && (
        <p>
          <Link to={`/${createdId}`}>Open the property &rarr;</Link>
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
          <h2 id="yad2-photos-heading">
            Photos found on the listing ({preview.image_urls.length})
          </h2>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={importPhotos}
              onChange={(e) => setImportPhotos(e.target.checked)}
            />
            <span>
              Save these photos to the property automatically (requires Google
              Drive connected in Settings)
            </span>
          </label>
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
