import { useId, useState, type KeyboardEvent } from 'react'

interface Props {
  value: string[]
  onChange: (next: string[]) => void
  suggestions?: string[]
}

export default function SegmentInput({ value, onChange, suggestions = [] }: Props) {
  const [draft, setDraft] = useState('')
  const listId = useId()

  function commit(raw: string): void {
    const next = raw
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && !value.includes(s))
    if (next.length === 0) return
    onChange([...value, ...next])
    setDraft('')
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>): void {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit(draft)
    } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  function remove(seg: string): void {
    onChange(value.filter((s) => s !== seg))
  }

  return (
    <div className="segment-input">
      <ul className="segment-tags" aria-label="Selected segments">
        {value.map((s) => (
          <li key={s} className="segment-tag">
            <span dir="auto">{s}</span>
            <button
              type="button"
              onClick={() => remove(s)}
              aria-label={`Remove ${s}`}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => commit(draft)}
        list={listId}
        placeholder="Type a segment and press Enter…"
        dir="auto"
      />
      {suggestions.length > 0 && (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
    </div>
  )
}
