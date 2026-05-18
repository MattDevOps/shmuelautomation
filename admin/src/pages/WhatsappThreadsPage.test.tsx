import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import WhatsappThreadsPage from './WhatsappThreadsPage'
import type {
  BotConfig,
  WhatsappThread,
  WhatsappThreadDetail,
  WhatsappThreadList,
} from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeThread(overrides: Partial<WhatsappThread> = {}): WhatsappThread {
  return {
    id: 't1',
    chat_jid: '972501234567@s.whatsapp.net',
    phone_number: '972501234567',
    display_name: 'Lead Person',
    mode: 'bot',
    takeover_reason: null,
    contact_id: null,
    last_bot_reply_at: null,
    last_message_at: '2026-05-18T07:00:00',
    created_at: '2026-05-18T06:00:00',
    updated_at: '2026-05-18T07:00:00',
    ...overrides,
  }
}

function botConfig(overrides: Partial<BotConfig> = {}): BotConfig {
  return {
    chatbot_enabled: false,
    greeting_he: null,
    greeting_en: null,
    takeover_notice_he: null,
    takeover_notice_en: null,
    updated_at: '2026-05-18T06:00:00',
    ...overrides,
  }
}

function detailFor(t: WhatsappThread): WhatsappThreadDetail {
  return {
    thread: t,
    messages: [
      {
        id: 'm1',
        message_id: 'M1',
        chat_jid: t.chat_jid,
        from_jid: t.chat_jid,
        from_phone: t.phone_number,
        from_name: t.display_name,
        text: 'Hi do you have anything in Baka?',
        media_type: null,
        is_group: false,
        wa_timestamp: 1_700_000_000,
        created_at: '2026-05-18T06:55:00',
      },
    ],
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WhatsappThreadsPage />
    </MemoryRouter>,
  )
}

describe('WhatsappThreadsPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders empty state when no threads', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ threads: [], total: 0 } as WhatsappThreadList))
      .mockResolvedValueOnce(jsonResponse(botConfig()))
    renderPage()
    expect(await screen.findByText(/no threads yet/i)).toBeInTheDocument()
  })

  it('shows thread list and opens detail on click', async () => {
    const t = makeThread()
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({ threads: [t], total: 1 } as WhatsappThreadList),
      )
      .mockResolvedValueOnce(jsonResponse(botConfig()))
      // auto-selection of first thread fetches its detail
      .mockResolvedValueOnce(jsonResponse(detailFor(t)))
    renderPage()
    expect(await screen.findByText('Lead Person')).toBeInTheDocument()
    expect(
      await screen.findByText('Hi do you have anything in Baka?'),
    ).toBeInTheDocument()
  })

  it('toggles chatbot enabled on/off via bot-config panel', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ threads: [], total: 0 }))
      .mockResolvedValueOnce(jsonResponse(botConfig({ chatbot_enabled: false })))
      // PATCH /whatsapp/bot-config returns updated row
      .mockResolvedValueOnce(jsonResponse(botConfig({ chatbot_enabled: true })))

    renderPage()
    const turnOn = await screen.findByRole('button', { name: /turn on/i })
    await userEvent.click(turnOn)

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) => c[0])
      const patchCall = calls.find(
        (c) => typeof c === 'string' && c.includes('/whatsapp/bot-config'),
      )
      expect(patchCall).toBeTruthy()
    })

    expect(
      await screen.findByRole('button', { name: /turn off/i }),
    ).toBeInTheDocument()
  })

  it('takeover button PATCHes thread to human mode', async () => {
    const t = makeThread({ mode: 'bot' })
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ threads: [t], total: 1 }))
      .mockResolvedValueOnce(jsonResponse(botConfig({ chatbot_enabled: true })))
      .mockResolvedValueOnce(jsonResponse(detailFor(t)))
      // PATCH /whatsapp/threads/t1
      .mockResolvedValueOnce(jsonResponse({ ...t, mode: 'human' }))
      // After reload, both endpoints re-fetched
      .mockResolvedValueOnce(
        jsonResponse({ threads: [{ ...t, mode: 'human' }], total: 1 }),
      )
      .mockResolvedValueOnce(jsonResponse(botConfig({ chatbot_enabled: true })))
      .mockResolvedValueOnce(jsonResponse(detailFor({ ...t, mode: 'human' })))

    renderPage()
    const takeover = await screen.findByRole('button', { name: /take over/i })
    await userEvent.click(takeover)
    await waitFor(() => {
      const patchCall = fetchSpy.mock.calls.find((c) => {
        const url = c[0]
        const init = c[1] as RequestInit | undefined
        return (
          typeof url === 'string' &&
          url.includes('/whatsapp/threads/t1') &&
          init?.method === 'PATCH'
        )
      })
      expect(patchCall).toBeTruthy()
      const body = JSON.parse(patchCall![1]!.body as string)
      expect(body).toEqual({ mode: 'human', takeover_reason: 'manual' })
    })
  })

  it('filters threads by mode tab', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ threads: [], total: 0 }))
      .mockResolvedValueOnce(jsonResponse(botConfig()))
      // click "Human" → re-fetches with mode=human
      .mockResolvedValueOnce(jsonResponse({ threads: [], total: 0 }))

    renderPage()
    const humanTab = await screen.findByRole('tab', { name: /human/i })
    await userEvent.click(humanTab)
    await waitFor(() => {
      const lastListCall = fetchSpy.mock.calls
        .map((c) => c[0])
        .reverse()
        .find(
          (u) =>
            typeof u === 'string' && u.includes('/whatsapp/threads') && !u.includes('bot-config'),
        )
      expect(lastListCall).toContain('mode=human')
    })
  })
})
