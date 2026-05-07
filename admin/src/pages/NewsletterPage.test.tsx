import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import NewsletterPage from './NewsletterPage'
import type { NewsletterSubscriber, SubscriberListResponse } from '../api/newsletter'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeSub(overrides: Partial<NewsletterSubscriber> = {}): NewsletterSubscriber {
  return {
    id: 's1',
    email: 'alice@example.com',
    language: 'en',
    type_filter: 'both',
    confirmed_at: null,
    unsubscribed_at: null,
    last_digest_at: null,
    source: 'wordpress',
    created_at: '2026-05-07T08:00:00',
    ...overrides,
  }
}

function makeResp(items: NewsletterSubscriber[]): SubscriberListResponse {
  const confirmed = items.filter((s) => s.confirmed_at && !s.unsubscribed_at).length
  const unsubscribed = items.filter((s) => s.unsubscribed_at).length
  const pending = items.length - confirmed - unsubscribed
  return {
    items,
    stats: { total: items.length, confirmed, pending, unsubscribed },
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <NewsletterPage />
    </MemoryRouter>,
  )
}

describe('NewsletterPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders empty state when no signups', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeResp([])))
    renderPage()
    expect(
      await screen.findByText(/no newsletter signups yet/i),
    ).toBeInTheDocument()
  })

  it('renders subscriber rows with stats', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        makeResp([
          makeSub({
            email: 'confirmed@example.com',
            confirmed_at: '2026-05-07T09:00:00',
          }),
          makeSub({ id: 's2', email: 'pending@example.com' }),
          makeSub({
            id: 's3',
            email: 'gone@example.com',
            confirmed_at: '2026-05-06T09:00:00',
            unsubscribed_at: '2026-05-07T08:00:00',
          }),
        ]),
      ),
    )
    renderPage()
    expect(await screen.findByText('confirmed@example.com')).toBeInTheDocument()
    expect(screen.getByText('pending@example.com')).toBeInTheDocument()
    expect(screen.getByText('gone@example.com')).toBeInTheDocument()
  })

  it('deletes a subscriber after confirmation', async () => {
    const sub = makeSub({ email: 'to-go@example.com' })
    fetchSpy
      .mockResolvedValueOnce(jsonResponse(makeResp([sub])))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(makeResp([])))

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()
    const button = await screen.findByLabelText('Delete to-go@example.com')
    await userEvent.click(button)

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining(`/newsletter/subscribers/${sub.id}`),
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
    confirmSpy.mockRestore()
  })
})
