import { useEffect, useState } from 'react'
import {
  createBlogPost,
  createNeighborhood,
  deleteBlogPost,
  deleteNeighborhood,
  listBlogPosts,
  listNeighborhoodContent,
  listSitePages,
  updateBlogPost,
  updateNeighborhood,
  updateSitePage,
} from '../api/content'
import type { BlogPost, NeighborhoodContent, SitePage } from '../api/types'

type Tab = 'blog' | 'neighborhoods' | 'pages'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'blog', label: 'Blog posts' },
  { key: 'neighborhoods', label: 'Neighbourhoods' },
  { key: 'pages', label: 'Pages' },
]

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleDateString('en-IL', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

/** Shared editor shell. Content is HTML because that is what came out of
 *  WordPress and what the site's components already render — swapping to a
 *  rich-text editor later changes only this component. */
function Editor({
  title,
  fields,
  body,
  onBody,
  onSave,
  onCancel,
  onDelete,
  busy,
  error,
}: {
  title: string
  fields: React.ReactNode
  body: string
  onBody: (v: string) => void
  onSave: () => void
  onCancel: () => void
  onDelete?: () => void
  busy: boolean
  error: string | null
}) {
  return (
    <div className="settings-card">
      <div className="card-title">{title}</div>
      <div className="content-fields">{fields}</div>
      <label className="content-body">
        Body (HTML)
        <textarea
          rows={14}
          value={body}
          onChange={(e) => onBody(e.target.value)}
          spellCheck
        />
      </label>
      {error ? <p className="error">{error}</p> : null}
      <div className="lead-actions">
        <button type="button" disabled={busy} onClick={onSave}>
          Save
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        {onDelete ? (
          <button type="button" className="danger" disabled={busy} onClick={onDelete}>
            Delete
          </button>
        ) : null}
      </div>
    </div>
  )
}

function BlogTab() {
  const [rows, setRows] = useState<BlogPost[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<BlogPost | 'new' | null>(null)
  const [draft, setDraft] = useState<Partial<BlogPost>>({})
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    listBlogPosts()
      .then((d) => !cancelled && setRows(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [tick])

  function open(row: BlogPost | 'new'): void {
    setEditing(row)
    setFormError(null)
    setDraft(row === 'new' ? { title: '', content_html: '', published: true } : { ...row })
  }

  async function save(): Promise<void> {
    setBusy(true)
    setFormError(null)
    try {
      if (editing === 'new') {
        await createBlogPost({
          title: draft.title,
          slug: draft.slug || undefined,
          content_html: draft.content_html ?? '',
          excerpt_html: draft.excerpt_html ?? null,
          image_url: draft.image_url ?? null,
          published: draft.published ?? true,
        })
      } else if (editing) {
        await updateBlogPost(editing.id, {
          title: draft.title,
          slug: draft.slug,
          content_html: draft.content_html,
          excerpt_html: draft.excerpt_html ?? null,
          image_url: draft.image_url ?? null,
          published: draft.published,
        })
      }
      setEditing(null)
      setTick((t) => t + 1)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function remove(): Promise<void> {
    if (editing === 'new' || editing === null) return
    if (!confirm(`Delete "${editing.title}"? This cannot be undone.`)) return
    setBusy(true)
    try {
      await deleteBlogPost(editing.id)
      setEditing(null)
      setTick((t) => t + 1)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  if (editing !== null) {
    return (
      <Editor
        title={editing === 'new' ? 'New blog post' : `Editing: ${editing.title}`}
        busy={busy}
        error={formError}
        body={draft.content_html ?? ''}
        onBody={(v) => setDraft((d) => ({ ...d, content_html: v }))}
        onSave={() => void save()}
        onCancel={() => setEditing(null)}
        onDelete={editing === 'new' ? undefined : () => void remove()}
        fields={
          <>
            <label>
              Title
              <input
                value={draft.title ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              />
            </label>
            <label>
              Web address (leave blank to build it from the title)
              <input
                value={draft.slug ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, slug: e.target.value }))}
                placeholder="a-day-in-baka"
              />
            </label>
            <label>
              Header image URL
              <input
                value={draft.image_url ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, image_url: e.target.value }))}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={draft.published ?? true}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, published: e.target.checked }))
                }
              />
              Visible on the website
            </label>
          </>
        }
      />
    )
  }

  return (
    <>
      <div className="lead-actions">
        <button type="button" onClick={() => open('new')}>
          New post
        </button>
      </div>
      {error ? <p className="error">Could not load posts: {error}</p> : null}
      {rows === null && !error ? <p className="muted">Loading…</p> : null}
      {rows?.length === 0 ? <p className="muted">No posts yet.</p> : null}
      {rows && rows.length > 0 ? (
        <table className="content-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Published</th>
              <th>Visible</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>{fmtDate(r.published_at)}</td>
                <td>{r.published ? 'Yes' : 'Draft'}</td>
                <td>
                  <button type="button" onClick={() => open(r)}>
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  )
}

function NeighborhoodsTab() {
  const [rows, setRows] = useState<NeighborhoodContent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<NeighborhoodContent | 'new' | null>(null)
  const [draft, setDraft] = useState<Partial<NeighborhoodContent>>({})
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    listNeighborhoodContent()
      .then((d) => !cancelled && setRows(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [tick])

  function open(row: NeighborhoodContent | 'new'): void {
    setEditing(row)
    setFormError(null)
    setDraft(
      row === 'new' ? { title: '', content_html: '', published: true, sort_order: 0 } : { ...row },
    )
  }

  async function save(): Promise<void> {
    setBusy(true)
    setFormError(null)
    try {
      const payload = {
        title: draft.title,
        slug: draft.slug || undefined,
        content_html: draft.content_html ?? '',
        card_image_url: draft.card_image_url ?? null,
        hero_image_url: draft.hero_image_url ?? null,
        sort_order: draft.sort_order ?? 0,
        published: draft.published ?? true,
      }
      if (editing === 'new') await createNeighborhood(payload)
      else if (editing) await updateNeighborhood(editing.id, payload)
      setEditing(null)
      setTick((t) => t + 1)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function remove(): Promise<void> {
    if (editing === 'new' || editing === null) return
    if (!confirm(`Delete "${editing.title}"? This cannot be undone.`)) return
    setBusy(true)
    try {
      await deleteNeighborhood(editing.id)
      setEditing(null)
      setTick((t) => t + 1)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  if (editing !== null) {
    return (
      <Editor
        title={editing === 'new' ? 'New neighbourhood' : `Editing: ${editing.title}`}
        busy={busy}
        error={formError}
        body={draft.content_html ?? ''}
        onBody={(v) => setDraft((d) => ({ ...d, content_html: v }))}
        onSave={() => void save()}
        onCancel={() => setEditing(null)}
        onDelete={editing === 'new' ? undefined : () => void remove()}
        fields={
          <>
            <label>
              Name
              <input
                value={draft.title ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              />
            </label>
            <label>
              Web address (leave blank to build it from the name)
              <input
                value={draft.slug ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, slug: e.target.value }))}
                placeholder="rehavia"
              />
            </label>
            <label>
              Card image URL
              <input
                value={draft.card_image_url ?? ''}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, card_image_url: e.target.value }))
                }
              />
            </label>
            <label>
              Header image URL (optional — falls back to the card image)
              <input
                value={draft.hero_image_url ?? ''}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, hero_image_url: e.target.value }))
                }
              />
            </label>
            <label>
              Order
              <input
                type="number"
                value={draft.sort_order ?? 0}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, sort_order: Number(e.target.value) }))
                }
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={draft.published ?? true}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, published: e.target.checked }))
                }
              />
              Visible on the website
            </label>
          </>
        }
      />
    )
  }

  return (
    <>
      <div className="lead-actions">
        <button type="button" onClick={() => open('new')}>
          New neighbourhood
        </button>
      </div>
      {error ? <p className="error">Could not load neighbourhoods: {error}</p> : null}
      {rows === null && !error ? <p className="muted">Loading…</p> : null}
      {rows && rows.length > 0 ? (
        <table className="content-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Order</th>
              <th>Visible</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>{r.sort_order}</td>
                <td>{r.published ? 'Yes' : 'Draft'}</td>
                <td>
                  <button type="button" onClick={() => open(r)}>
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  )
}

function PagesTab() {
  const [rows, setRows] = useState<SitePage[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<SitePage | null>(null)
  const [draft, setDraft] = useState<Partial<SitePage>>({})
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    listSitePages()
      .then((d) => !cancelled && setRows(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [tick])

  async function save(): Promise<void> {
    if (!editing) return
    setBusy(true)
    setFormError(null)
    try {
      await updateSitePage(editing.id, {
        title: draft.title,
        content_html: draft.content_html,
        published: draft.published,
      })
      setEditing(null)
      setTick((t) => t + 1)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  if (editing !== null) {
    return (
      <Editor
        title={`Editing: ${editing.title}`}
        busy={busy}
        error={formError}
        body={draft.content_html ?? ''}
        onBody={(v) => setDraft((d) => ({ ...d, content_html: v }))}
        onSave={() => void save()}
        onCancel={() => setEditing(null)}
        fields={
          <>
            <label>
              Title
              <input
                value={draft.title ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              />
            </label>
            <p className="muted">
              Web address: <code>/{editing.slug}/</code> — fixed, because the site
              links to it.
            </p>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={draft.published ?? true}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, published: e.target.checked }))
                }
              />
              Visible on the website
            </label>
          </>
        }
      />
    )
  }

  return (
    <>
      <p className="muted">
        The fixed pages of the site. Contact details and image sliders on these
        pages are kept as they are — editing the text here does not touch them.
      </p>
      {error ? <p className="error">Could not load pages: {error}</p> : null}
      {rows === null && !error ? <p className="muted">Loading…</p> : null}
      {rows && rows.length > 0 ? (
        <table className="content-table">
          <thead>
            <tr>
              <th>Page</th>
              <th>Address</th>
              <th>Visible</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>
                  <code>/{r.slug}/</code>
                </td>
                <td>{r.published ? 'Yes' : 'Hidden'}</td>
                <td>
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(r)
                      setDraft({ ...r })
                      setFormError(null)
                    }}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  )
}

export default function ContentPage() {
  const [tab, setTab] = useState<Tab>('blog')
  return (
    <section>
      <h2>Website content</h2>
      <p className="muted">
        Blog posts, neighbourhood guides and the fixed pages. These are not live
        on the website yet — the site still shows the WordPress versions until we
        switch it over.
      </p>
      <div className="filter-row">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={tab === t.key ? 'active' : ''}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'blog' ? <BlogTab /> : null}
      {tab === 'neighborhoods' ? <NeighborhoodsTab /> : null}
      {tab === 'pages' ? <PagesTab /> : null}
    </section>
  )
}
