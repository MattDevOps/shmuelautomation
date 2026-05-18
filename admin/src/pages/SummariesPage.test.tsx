import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import SummariesPage from './SummariesPage'
import type { ConversationSummary, ConversationSummaryList } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeSummary(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 's1',
    chat_jid: '972501234567@s.whatsapp.net',
    phone_number: '972501234567',
    contact_id: null,
    period_start: '2026-05-17T08:00:00',
    period_end: '2026-05-18T08:00:00',
    message_count: 4,
    summary: 'Lead asked about a 3BR rental in Talbiya.',
    action_items: ['Send 2-3 matches'],
    mentioned_amounts: ['12000 NIS'],
    mentioned_dates: ['Tuesday'],
    created_at: '2026-05-18T08:00:01',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SummariesPage />
    </MemoryRouter>,
  )
}

describe('SummariesPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders empty state when no summaries', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ summaries: [], total: 0 } as ConversationSummaryList),
    )
    renderPage()
    expect(await screen.findByText(/no summaries yet/i)).toBeInTheDocument()
  })

  it('renders summary cards with action items + pills', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        summaries: [makeSummary()],
        total: 1,
      } as ConversationSummaryList),
    )
    renderPage()
    expect(
      await screen.findByText(/Lead asked about a 3BR rental in Talbiya/),
    ).toBeInTheDocument()
    expect(screen.getByText('Send 2-3 matches')).toBeInTheDocument()
    expect(screen.getByText('12000 NIS')).toBeInTheDocument()
    expect(screen.getByText('Tuesday')).toBeInTheDocument()
  })

  it('summarize-now button POSTs and re-fetches', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ summaries: [], total: 0 }))
      // POST run → result
      .mockResolvedValueOnce(
        jsonResponse({ attempted: 1, summarized: 1, skipped: 0, threads: [] }),
      )
      // Reload after run
      .mockResolvedValueOnce(
        jsonResponse({ summaries: [makeSummary()], total: 1 }),
      )

    renderPage()
    const btn = await screen.findByRole('button', { name: /summarize now/i })
    await userEvent.click(btn)

    await waitFor(() => {
      expect(
        screen.getByText(/1 summarized, 0 skipped of 1 threads/i),
      ).toBeInTheDocument()
    })
  })

  it('send-digest button reports the result', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ summaries: [], total: 0 }))
      .mockResolvedValueOnce(jsonResponse({ sent: false, reason: 'no_recipient' }))

    renderPage()
    const btn = await screen.findByRole('button', { name: /send daily digest/i })
    await userEvent.click(btn)
    await waitFor(() => {
      expect(screen.getByText(/no_recipient/i)).toBeInTheDocument()
    })
  })
})
