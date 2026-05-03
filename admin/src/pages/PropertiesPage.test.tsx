import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import PropertiesPage from './PropertiesPage'
import type { Property } from '../api/types'

function makeProperty(overrides: Partial<Property> = {}): Property {
  return {
    id: 'p1',
    type: 'rent',
    status: 'available',
    price: '8500.00',
    currency: 'ILS',
    rooms: '3.5',
    size_sqm: 80,
    floor: null,
    address: null,
    neighborhood: 'Baka',
    city: 'Jerusalem',
    owner_name: 'Yossi',
    owner_phone: null,
    broker_fee_status: 'yes',
    broker_fee_amount: null,
    description: null,
    notes: null,
    yad2_url: null,
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
    ...overrides,
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PropertiesPage />
    </MemoryRouter>,
  )
}

describe('PropertiesPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders rows from the backend', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([
        makeProperty({ neighborhood: 'Baka' }),
        makeProperty({ id: 'p2', neighborhood: 'Katamon' }),
      ]),
    )
    renderPage()

    expect(await screen.findByText('Baka')).toBeInTheDocument()
    expect(screen.getByText('Katamon')).toBeInTheDocument()
  })

  it('shows empty state when backend returns no rows', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    renderPage()
    expect(await screen.findByText(/no properties match/i)).toBeInTheDocument()
  })

  it('shows error banner when backend fails', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ detail: 'boom' }, 500),
    )
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('refetches with type filter when select changes', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]))
    renderPage()

    await screen.findByText(/no properties match/i)
    const filtersGroup = screen.getByRole('group', { name: /filter/i })
    const typeSelect = within(filtersGroup).getByLabelText(/type/i)
    await userEvent.selectOptions(typeSelect, 'rent')

    await waitFor(() => {
      const lastCall = fetchSpy.mock.calls.at(-1)
      expect(lastCall?.[0]).toMatch(/type=rent/)
    })
  })

  it('flips status via row select', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeProperty({ neighborhood: 'Baka' })]))
      .mockResolvedValueOnce(
        jsonResponse(makeProperty({ neighborhood: 'Baka', status: 'rented' })),
      )
    renderPage()

    const select = await screen.findByLabelText(/Status for Baka/i)
    await userEvent.selectOptions(select, 'rented')

    await waitFor(() => {
      const patchCall = fetchSpy.mock.calls.find(
        ([, init]) =>
          (init as RequestInit | undefined)?.method === 'PATCH',
      )
      expect(patchCall).toBeDefined()
      expect(JSON.parse((patchCall![1] as RequestInit).body as string)).toEqual(
        { status: 'rented' },
      )
    })
  })

  it('deletes a row after confirm', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeProperty({ neighborhood: 'Baka' })]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    const btn = await screen.findByRole('button', { name: /delete baka/i })
    await userEvent.click(btn)

    await waitFor(() => {
      expect(screen.queryByText('Baka')).not.toBeInTheDocument()
    })
  })

  it('renders an Export to Excel link pointing at the backend export endpoint', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    renderPage()

    const link = await screen.findByRole('link', { name: /export to excel/i })
    expect(link.getAttribute('href')).toMatch(/\/properties\/export$/)
  })

  it('does not delete when user cancels confirm', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([makeProperty({ neighborhood: 'Baka' })]),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()

    const btn = await screen.findByRole('button', { name: /delete baka/i })
    await userEvent.click(btn)
    expect(screen.getByText('Baka')).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })
})
