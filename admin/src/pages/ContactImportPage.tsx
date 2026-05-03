import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { importContactsCSV } from '../api/contacts'
import type { ContactImportResult } from '../api/types'

const STATUS_LABELS: Record<string, string> = {
  create: 'Will create',
  created: 'Created',
  duplicate: 'Duplicate — skipped',
  error: 'Error — skipped',
}

export default function ContactImportPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ContactImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handlePreview(e: FormEvent): Promise<void> {
    e.preventDefault()
    if (!file) return
    setError(null)
    setBusy(true)
    try {
      const result = await importContactsCSV(file, true)
      setPreview(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not parse CSV.')
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleApply(): Promise<void> {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await importContactsCSV(file, false)
      navigate('/contacts')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Import contacts</h1>
          <p className="page-subhead">
            Upload a CSV exported from Excel, Bambi, Nadlan ONE, or your
            current address book. Required column: <code>Name</code>. Optional:{' '}
            <code>Phone</code>, <code>Email</code>, <code>Language</code>,{' '}
            <code>Segments</code> (semicolon-separated), <code>Notes</code>.
          </p>
        </div>
      </header>

      <form
        onSubmit={(e) => void handlePreview(e)}
        className="import-form"
        aria-label="Choose contacts CSV"
      >
        <label className="field">
          <span className="label-text">CSV file</span>
          <input
            type="file"
            accept=".csv,text/csv"
            required
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setPreview(null)
            }}
          />
        </label>
        <button
          type="submit"
          className="btn-primary"
          disabled={busy || !file}
        >
          {busy && !preview ? 'Reading…' : 'Preview'}
        </button>
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {preview && <PreviewTable result={preview} onApply={() => void handleApply()} busy={busy} />}
    </section>
  )
}

interface PreviewProps {
  result: ContactImportResult
  onApply: () => void
  busy: boolean
}

function PreviewTable({ result, onApply, busy }: PreviewProps): React.ReactElement {
  const { summary, rows } = result
  const hasCreates = summary.would_create > 0
  const allDone = rows.every((r) => r.status === 'created')

  return (
    <section className="import-preview" aria-labelledby="preview-heading">
      <h2 id="preview-heading">
        {allDone ? 'Imported' : 'Preview'}
      </h2>
      <ul className="import-summary">
        <li>
          <strong>{summary.total_rows}</strong> rows in file
        </li>
        <li>
          <strong className="num-create">{summary.would_create}</strong>{' '}
          {allDone ? 'created' : 'will be created'}
        </li>
        <li>
          <strong className="num-dup">{summary.would_skip_duplicates}</strong>{' '}
          skipped (duplicates)
        </li>
        <li>
          <strong className="num-err">{summary.errors}</strong> errors
        </li>
      </ul>

      {!allDone && hasCreates && (
        <div className="form-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={onApply}
            disabled={busy}
          >
            {busy
              ? 'Importing…'
              : `Apply — create ${summary.would_create} contact${
                  summary.would_create === 1 ? '' : 's'
                }`}
          </button>
        </div>
      )}

      <div className="table-scroll">
        <table className="properties-table">
          <thead>
            <tr>
              <th scope="col">Row</th>
              <th scope="col">Status</th>
              <th scope="col">Name</th>
              <th scope="col">Phone</th>
              <th scope="col">Segments</th>
              <th scope="col">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.row_number} data-status={r.status}>
                <td className="num">{r.row_number}</td>
                <td>
                  <span className={`status-pill-${r.status}`}>
                    {STATUS_LABELS[r.status] ?? r.status}
                  </span>
                  {r.detail && (
                    <span className="muted" style={{ marginLeft: 8 }}>
                      {r.detail}
                    </span>
                  )}
                </td>
                <td dir="auto">{r.name || <span className="dim">—</span>}</td>
                <td className="num">{r.phone ?? <span className="dim">—</span>}</td>
                <td>{r.segments.join(', ') || <span className="dim">—</span>}</td>
                <td dir="auto">
                  {r.notes ? (
                    r.notes.length > 60 ? (
                      `${r.notes.slice(0, 60)}…`
                    ) : (
                      r.notes
                    )
                  ) : (
                    <span className="dim">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
