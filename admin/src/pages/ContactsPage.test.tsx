import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ContactsPage from './ContactsPage'
import type { Contact } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeContact(overrides: Partial<Contact> = {}): Contact {
  return {
    id: 'c1',
    name: 'Yossi Cohen',
    phone: '+972500000000',
    email: null,
    language: 'he',
    segments: ['buyer'],
    notes: null,
    source: 'manual',
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ContactsPage />
    </MemoryRouter>,
  )
}

describe('ContactsPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders contacts from the backend', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse(['buyer', 'renter'])) // segments
      .mockResolvedValueOnce(jsonResponse([makeContact({ name: 'Yossi' })])) // contacts

    renderPage()
    expect(await screen.findByText('Yossi')).toBeInTheDocument()
  })

  it('toggles a segment filter and refetches', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse(['buyer', 'vip']))
      .mockResolvedValueOnce(jsonResponse([])) // initial list
      .mockResolvedValue(jsonResponse([makeContact()])) // after filter

    renderPage()
    // Wait for the segment chips to render
    const chip = await screen.findByRole('button', { name: 'buyer' })
    await userEvent.click(chip)

    await waitFor(() => {
      const url = fetchSpy.mock.calls.at(-1)?.[0] as string
      expect(url).toMatch(/segment=buyer/)
    })
  })

  it('export link reflects the active segment filter', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse(['buyer']))
      .mockResolvedValueOnce(jsonResponse([]))
    renderPage()
    await screen.findByRole('button', { name: 'buyer' })
    await userEvent.click(screen.getByRole('button', { name: 'buyer' }))

    const link = await screen.findByRole('link', { name: /export \(buyer\)/i })
    expect(link.getAttribute('href')).toMatch(
      /\/contacts\/export\.csv\?segment=buyer$/,
    )
  })

  it('shows empty state with a helpful message', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse([]))
    renderPage()
    expect(await screen.findByText(/no contacts yet/i)).toBeInTheDocument()
  })

  it('deletes a contact after confirm', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([])) // segments
      .mockResolvedValueOnce(jsonResponse([makeContact({ name: 'Yossi' })])) // contacts
      .mockResolvedValueOnce(new Response(null, { status: 204 })) // delete
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /delete yossi/i }),
    )
    await waitFor(() => {
      expect(screen.queryByText('Yossi')).not.toBeInTheDocument()
    })
  })
})
