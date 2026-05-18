import { useEffect, useMemo, useState } from 'react'
import {
  getBotConfig,
  getThread,
  listThreads,
  updateBotConfig,
  updateThreadMode,
} from '../api/whatsapp-threads'
import type {
  BotConfig,
  ThreadMode,
  WhatsappThread,
  WhatsappThreadDetail,
  WhatsappThreadList,
} from '../api/types'

type FilterKey = 'all' | ThreadMode

function fmt(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IL', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function threadTitle(t: WhatsappThread): string {
  return t.display_name?.trim() || t.phone_number || t.chat_jid
}

export default function WhatsappThreadsPage() {
  const [list, setList] = useState<WhatsappThreadList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [reloadTick, setReloadTick] = useState(0)
  // `userSelectedId` is what the user has explicitly clicked. If unset, the
  // effective selection falls back to the first thread in `list` — derived
  // at render time so we never have to setState from inside an effect.
  const [userSelectedId, setUserSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<WhatsappThreadDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [cfg, setCfg] = useState<BotConfig | null>(null)
  const [cfgSaving, setCfgSaving] = useState(false)

  const reload = (): void => setReloadTick((t) => t + 1)
  const selectedId =
    userSelectedId ?? (list && list.threads.length > 0 ? list.threads[0].id : null)

  useEffect(() => {
    let cancelled = false
    listThreads({ mode: filter === 'all' ? undefined : filter })
      .then((data) => {
        if (cancelled) return
        setList(data)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setList({ threads: [], total: 0 })
        setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [filter, reloadTick])

  useEffect(() => {
    let cancelled = false
    getBotConfig()
      .then((c) => {
        if (!cancelled) setCfg(c)
      })
      .catch(() => {
        if (!cancelled) setCfg(null)
      })
    return () => {
      cancelled = true
    }
  }, [reloadTick])

  useEffect(() => {
    if (selectedId === null) {
      return
    }
    let cancelled = false
    getThread(selectedId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        setDetailError(null)
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setDetail(null)
          setDetailError(e.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [selectedId, reloadTick])

  async function handleToggleMode(thread: WhatsappThread): Promise<void> {
    const next: ThreadMode = thread.mode === 'bot' ? 'human' : 'bot'
    await updateThreadMode(thread.id, {
      mode: next,
      takeover_reason: next === 'human' ? 'manual' : null,
    })
    reload()
  }

  async function handleToggleChatbot(): Promise<void> {
    if (cfg === null) return
    setCfgSaving(true)
    try {
      const updated = await updateBotConfig({ chatbot_enabled: !cfg.chatbot_enabled })
      setCfg(updated)
    } finally {
      setCfgSaving(false)
    }
  }

  const threads = useMemo(() => list?.threads ?? [], [list])

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>WhatsApp chatbot</h1>
          <p className="page-subhead">
            Inbound 1:1 conversations the bot has seen. Threads flip to{' '}
            <strong>Human</strong> as soon as a lead asks something the bot
            shouldn&rsquo;t auto-answer. Release a thread back to the bot
            once you&rsquo;ve replied yourself.
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={reload}>
            Refresh
          </button>
        </div>
      </header>

      <BotConfigPanel
        cfg={cfg}
        saving={cfgSaving}
        onToggle={handleToggleChatbot}
      />

      {error && (
        <p role="alert" className="error">
          Could not load threads: {error}
        </p>
      )}

      <div className="thread-toolbar">
        <FilterTabs filter={filter} onChange={setFilter} />
        <span className="thread-count">
          {list === null ? '…' : `${list.total} thread${list.total === 1 ? '' : 's'}`}
        </span>
      </div>

      {list === null ? (
        <div className="callout">
          <p className="callout-display">Loading…</p>
        </div>
      ) : threads.length === 0 ? (
        <div className="callout">
          <p className="callout-display">No threads yet</p>
          <p>
            The chatbot will start tracking conversations the moment the
            daemon is paired and the first inbound DM arrives.
          </p>
        </div>
      ) : (
        <div className="thread-layout">
          <ThreadList
            threads={threads}
            selectedId={selectedId}
            onSelect={setUserSelectedId}
          />
          <ThreadDetailPanel
            detail={detail}
            error={detailError}
            onToggleMode={handleToggleMode}
          />
        </div>
      )}
    </section>
  )
}

function BotConfigPanel({
  cfg,
  saving,
  onToggle,
}: {
  cfg: BotConfig | null
  saving: boolean
  onToggle: () => void
}): React.ReactElement | null {
  if (cfg === null) {
    return (
      <div className="callout">
        <p className="callout-display">Bot config unavailable</p>
        <p>The backend didn&rsquo;t return a config row. Refresh in a moment.</p>
      </div>
    )
  }
  return (
    <div className="bot-config-bar">
      <div>
        <span className="label-eyebrow">Chatbot</span>
        <p className="bot-config-state" data-on={cfg.chatbot_enabled}>
          {cfg.chatbot_enabled ? 'On — auto-replying to leads' : 'Off — bot silent'}
        </p>
      </div>
      <button
        type="button"
        className={cfg.chatbot_enabled ? 'btn-danger' : 'btn-primary'}
        onClick={onToggle}
        disabled={saving}
      >
        {cfg.chatbot_enabled ? 'Turn off' : 'Turn on'}
      </button>
    </div>
  )
}

function FilterTabs({
  filter,
  onChange,
}: {
  filter: FilterKey
  onChange: (f: FilterKey) => void
}): React.ReactElement {
  const tabs: { key: FilterKey; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'bot', label: 'Bot' },
    { key: 'human', label: 'Human (takeover)' },
  ]
  return (
    <div className="thread-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={filter === t.key}
          className={filter === t.key ? 'thread-tab is-active' : 'thread-tab'}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function ThreadList({
  threads,
  selectedId,
  onSelect,
}: {
  threads: WhatsappThread[]
  selectedId: string | null
  onSelect: (id: string) => void
}): React.ReactElement {
  return (
    <ul className="thread-list">
      {threads.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            className={
              selectedId === t.id
                ? 'thread-list-item is-active'
                : 'thread-list-item'
            }
            onClick={() => onSelect(t.id)}
          >
            <span className="thread-list-name">{threadTitle(t)}</span>
            <span
              className={
                t.mode === 'human'
                  ? 'thread-mode-pill thread-mode-human'
                  : 'thread-mode-pill thread-mode-bot'
              }
            >
              {t.mode === 'human' ? 'Human' : 'Bot'}
            </span>
            <span className="thread-list-time">{fmt(t.last_message_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function ThreadDetailPanel({
  detail,
  error,
  onToggleMode,
}: {
  detail: WhatsappThreadDetail | null
  error: string | null
  onToggleMode: (t: WhatsappThread) => void
}): React.ReactElement {
  if (error) {
    return (
      <div className="thread-detail">
        <p role="alert" className="error">
          {error}
        </p>
      </div>
    )
  }
  if (detail === null) {
    return (
      <div className="thread-detail">
        <p className="page-subhead">Select a thread to see the conversation.</p>
      </div>
    )
  }
  const { thread, messages } = detail
  return (
    <div className="thread-detail">
      <header className="thread-detail-header">
        <div>
          <h2>{threadTitle(thread)}</h2>
          <p className="page-subhead">
            {thread.phone_number ? `+${thread.phone_number}` : thread.chat_jid}
            {thread.takeover_reason && (
              <>
                {' '}
                · takeover: <em>{thread.takeover_reason}</em>
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          className={thread.mode === 'bot' ? 'btn-danger' : 'btn-primary'}
          onClick={() => onToggleMode(thread)}
        >
          {thread.mode === 'bot' ? 'Take over' : 'Release to bot'}
        </button>
      </header>

      {messages.length === 0 ? (
        <p className="page-subhead">No messages yet on this thread.</p>
      ) : (
        <ol className="thread-messages">
          {messages.map((m) => (
            <li key={m.id} className="thread-message">
              <span className="thread-message-time">
                {fmt(m.created_at)}
              </span>
              <span className="thread-message-text">
                {m.text ?? <em>({m.media_type ?? 'no text'})</em>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
