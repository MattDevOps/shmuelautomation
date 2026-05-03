import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import QueuePage from './QueuePage'
import type { PostSlotWithProperty } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeSlot(overrides: Partial<PostSlotWithProperty> = {}): PostSlotWithProperty {
  return {
    id: 's1',
    property_id: 'p1',
    scheduled_for: '2030-05-08T17:00:00',  // far future = "Upcoming"
    status: 'pending',
    priority: 200,
    posted_at: null,
    created_at: '2026-05-03T00:00:00',
    property_type: 'rent',
    property_neighborhood: 'Baka',
    property_address: null,
    property_price: '8500.00',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <QueuePage />
    </MemoryRouter>,
  )
}

describe('QueuePage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders empty state when no slots are queued', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    renderPage()
    expect(
      await screen.findByText(/nothing in the queue yet/i),
    ).toBeInTheDocument()
  })

  it('separates due-now from upcoming slots', async () => {
    const past = new Date(Date.now() - 60 * 60 * 1000).toISOString().replace('Z', '')
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([
        makeSlot({ id: 'overdue', scheduled_for: past, property_neighborhood: 'OverdueHood' }),
        makeSlot({ id: 'future', property_neighborhood: 'FutureHood' }),
      ]),
    )
    renderPage()

    expect(await screen.findByRole('heading', { name: /due now/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /upcoming/i })).toBeInTheDocument()
    expect(screen.getByText('OverdueHood')).toBeInTheDocument()
    expect(screen.getByText('FutureHood')).toBeInTheDocument()
  })

  it('opens the share modal when Compose & share is clicked', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeSlot()]))
      .mockResolvedValueOnce(
        jsonResponse({
          text_en: 'For rent — Baka',
          text_he: 'להשכרה',
          whatsapp_share_url: 'https://wa.me/?text=x',
          facebook_share_url: null,
        }),
      )
    renderPage()
    await userEvent.click(
      await screen.findByRole('button', { name: /compose and share baka/i }),
    )
    expect(
      await screen.findByRole('dialog', { name: /share property/i }),
    ).toBeInTheDocument()
    expect(await screen.findByDisplayValue(/for rent/i)).toBeInTheDocument()
  })

  it('Skip calls the API and refreshes', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeSlot()])) // initial
      .mockResolvedValueOnce(jsonResponse({ id: 's1', status: 'skipped' })) // skip
      .mockResolvedValueOnce(jsonResponse([])) // refresh: empty
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    await screen.findByText('Baka')
    await userEvent.click(screen.getByRole('button', { name: /^skip$/i }))

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) => c[0]) as string[]
      expect(calls.some((u) => /\/post-queue\/s1\/skip$/.test(u))).toBe(true)
    })
  })

  it('Cancel calls DELETE and removes the row', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeSlot()]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse([]))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    await screen.findByText('Baka')
    await userEvent.click(screen.getByRole('button', { name: /^cancel$/i }))

    await waitFor(() => {
      expect(screen.queryByText('Baka')).not.toBeInTheDocument()
    })
  })

  it('shows an error banner when listQueue fails', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'boom' }, 500))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})
