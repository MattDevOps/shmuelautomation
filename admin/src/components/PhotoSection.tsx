import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { deletePhoto, listPhotos, uploadPhoto } from '../api/cloud'
import type { CloudPhoto } from '../api/types'

interface Props {
  propertyId: string
}

interface UploadFailure {
  fileName: string
  message: string
}

function thumbnailFor(p: {
  thumbnail_url: string | null
  external_id: string
}): string {
  // Drive may not have rendered the thumbnail at upload time; this stable URL
  // always resolves for the file owner (Shmuel logged into Drive in the same
  // browser). Falls back to whatever we stored if Drive populated it.
  return (
    p.thumbnail_url ??
    `https://drive.google.com/thumbnail?id=${p.external_id}&sz=w400`
  )
}

export default function PhotoSection({ propertyId }: Props) {
  const [photos, setPhotos] = useState<CloudPhoto[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [uploading, setUploading] = useState<string[]>([])
  const [failures, setFailures] = useState<UploadFailure[]>([])
  const [driveDisconnected, setDriveDisconnected] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    listPhotos(propertyId)
      .then((rows) => {
        if (!cancelled) setPhotos(rows)
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setPhotos([])
          setLoadError(e.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [propertyId])

  async function handleFiles(files: FileList | null): Promise<void> {
    if (!files || files.length === 0) return
    setFailures([])
    const fileArr = Array.from(files)
    setUploading(fileArr.map((f) => f.name))

    for (const file of fileArr) {
      try {
        const row = await uploadPhoto(propertyId, file)
        setPhotos((prev) => {
          if (prev === null) return [row]
          if (prev.some((p) => p.id === row.id)) return prev
          return [row, ...prev]
        })
      } catch (e) {
        if (e instanceof ApiError && e.status === 412) {
          setDriveDisconnected(true)
        }
        setFailures((prev) => [
          ...prev,
          {
            fileName: file.name,
            message: e instanceof Error ? e.message : 'Upload failed.',
          },
        ])
      } finally {
        setUploading((prev) => prev.filter((n) => n !== file.name))
      }
    }

    if (inputRef.current) inputRef.current.value = ''
  }

  async function handleDelete(photo: CloudPhoto): Promise<void> {
    if (!confirm(`Delete ${photo.file_name}? It will move to Drive trash.`))
      return
    const previous = photos
    setPhotos((prev) => prev?.filter((p) => p.id !== photo.id) ?? null)
    try {
      await deletePhoto(propertyId, photo.id)
    } catch (e) {
      setPhotos(previous)
      setLoadError(e instanceof Error ? e.message : 'Delete failed.')
    }
  }

  return (
    <section className="photos-section" aria-labelledby="photos-heading">
      <h2 id="photos-heading">Photos</h2>
      <p className="muted">
        Uploaded to your own Google Drive. One folder per property,
        recoverable from Drive trash.
      </p>

      {driveDisconnected && (
        <p role="alert" className="error">
          Google Drive is not connected.{' '}
          <Link to="/settings">Connect it in Settings</Link> before uploading.
        </p>
      )}

      <label className="photo-upload">
        <span className="upload-eyebrow">Upload photos</span>
        <span className="upload-prompt">
          Choose JPG, PNG, or HEIC files from your computer
        </span>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => void handleFiles(e.target.files)}
          disabled={uploading.length > 0}
        />
      </label>

      {uploading.length > 0 && (
        <p role="status" className="muted">
          Uploading {uploading.length} photo
          {uploading.length === 1 ? '' : 's'}…
        </p>
      )}

      {failures.length > 0 && (
        <div role="alert" className="warnings">
          <span className="warnings-heading">
            Some photos didn&rsquo;t upload
          </span>
          <ul>
            {failures.map((f, i) => (
              <li key={i}>
                <strong>{f.fileName}</strong>: {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loadError && (
        <p role="alert" className="error">
          {loadError}
        </p>
      )}

      {photos === null ? (
        <p className="muted">Loading photos…</p>
      ) : photos.length === 0 ? (
        <p className="muted">No photos yet.</p>
      ) : (
        <ul className="photo-grid">
          {photos.map((p) => (
            <li key={p.id} className="photo-tile">
              <div className="photo-tile-image">
                {p.external_id ? (
                  <img
                    src={thumbnailFor(p)}
                    alt={p.file_name}
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="photo-fallback" aria-label={p.file_name}>
                    {p.file_name}
                  </div>
                )}
              </div>
              <div className="photo-tile-actions">
                {p.web_view_url ? (
                  <a
                    href={p.web_view_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open in Drive
                  </a>
                ) : (
                  <span />
                )}
                <button
                  type="button"
                  onClick={() => void handleDelete(p)}
                  aria-label={`Delete ${p.file_name}`}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
