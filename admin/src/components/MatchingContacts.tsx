import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listMatchingContacts } from '../api/properties'
import type { ContactMatch } from '../api/types'

interface Props {
  propertyId: string
}

export default function MatchingContacts({ propertyId }: Props) {
  const [matches, setMatches] = useState<ContactMatch[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listMatchingContacts(propertyId)
      .then((rows) => {
        if (!cancelled) setMatches(rows)
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setMatches([])
          setError(e.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [propertyId])

  return (
    <section
      className="matching-contacts"
      aria-labelledby="matching-contacts-heading"
    >
      <h2 id="matching-contacts-heading">Matching contacts</h2>
      <p className="muted">
        People in your address book whose tags align with this property —
        the natural first call when you have something they might want.
      </p>

      {error && (
        <p role="alert" className="error">
          Could not load matches: {error}
        </p>
      )}

      {matches === null ? (
        <p className="muted">Loading…</p>
      ) : matches.length === 0 ? (
        <p className="muted">
          No matches yet. Tag contacts with the neighborhood (e.g.{' '}
          <em>baka</em>) and audience (<em>buyer</em> / <em>renter</em>) to
          surface them here.
        </p>
      ) : (
        <ul className="match-list">
          {matches.map((m) => (
            <li key={m.id} className="match-row">
              <div className="match-row-main">
                <Link to={`/contacts/${m.id}`} className="match-name" dir="auto">
                  {m.name}
                </Link>
                <span className="match-reasons">
                  matched by{' '}
                  {m.match_reasons.map((reason, i) => (
                    <span key={reason}>
                      {i > 0 && ' + '}
                      <em dir="auto">{reason}</em>
                    </span>
                  ))}
                </span>
              </div>
              <div className="match-row-actions">
                {m.phone && (
                  <a href={`tel:${m.phone.replace(/\s+/g, '')}`}>
                    {m.phone}
                  </a>
                )}
                {m.phone && (
                  <a
                    href={`https://wa.me/${m.phone.replace(/[^\d]/g, '')}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    WhatsApp
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
