import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import LeadsPage from './LeadsPage'
import type { Lead } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeLead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: 'l1',
    source: 'call',
    source_ref: 'call-1',
    phone: '972501234567',
    display_name: 'Dana',
    summary: 'Wants a 3 bedroom in City Center.',
    requirements: {
      rooms: '3 bedrooms',
      neighborhoods: ['City Center'],
      parking: true,
      household: 'family of 6',
    },
    status: 'pending',
    contact_id: null,
    reviewed_at: null,
    created_at: '2026-09-01T09:00:00',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LeadsPage />
    </MemoryRouter>,
  )
}

describe('LeadsPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the requirements a lead stated', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ items: [makeLead()], total: 1, pending: 1 }),
    )
    renderPage()

    expect(await screen.findByText('Dana')).toBeInTheDocument()
    expect(screen.getByText('3 bedrooms')).toBeInTheDocument()
    expect(screen.getByText('City Center')).toBeInTheDocument()
    expect(screen.getByText('family of 6')).toBeInTheDocument()
  })

  it('renders booleans as words, never true/false', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ items: [makeLead()], total: 1, pending: 1 }),
    )
    renderPage()

    expect(await screen.findByText('yes')).toBeInTheDocument()
    expect(screen.queryByText('true')).not.toBeInTheDocument()
  })

  it('says so plainly when a lead stated nothing specific', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({
        items: [makeLead({ requirements: {} })],
        total: 1,
        pending: 1,
      }),
    )
    renderPage()

    expect(
      await screen.findByText(/No specific requirements were stated/i),
    ).toBeInTheDocument()
  })

  it('approving posts to the approve endpoint', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({ items: [makeLead()], total: 1, pending: 1 }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          lead: makeLead({ status: 'approved', contact_id: 'c1' }),
          contact_id: 'c1',
        }),
      )
      .mockResolvedValue(jsonResponse({ items: [], total: 0, pending: 0 }))

    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /add to contacts/i }))

    await waitFor(() => {
      const called = fetchSpy.mock.calls.map((c) => String(c[0]))
      expect(called.some((u) => u.endsWith('/leads/l1/approve'))).toBe(true)
    })
  })

  it('shows the pending count on the filter', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ items: [makeLead()], total: 4, pending: 3 }),
    )
    renderPage()
    expect(await screen.findByRole('button', { name: /Needs review \(3\)/ })).toBeInTheDocument()
  })

  it('an approved lead links through to its contact', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({
        items: [makeLead({ status: 'approved', contact_id: 'c9' })],
        total: 1,
        pending: 0,
      }),
    )
    renderPage()
    const link = await screen.findByRole('link', { name: /view the contact/i })
    expect(link).toHaveAttribute('href', '/contacts/c9')
  })
})
