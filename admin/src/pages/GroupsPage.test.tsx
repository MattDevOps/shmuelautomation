import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import GroupsPage from './GroupsPage'
import type { Group } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: 'g1',
    platform: 'whatsapp',
    audience: 'rent',
    name: 'Baka Rentals WA',
    target_url: 'https://chat.whatsapp.com/abc',
    notes: null,
    sort_order: 0,
    active: true,
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <GroupsPage />
    </MemoryRouter>,
  )
}

describe('GroupsPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders empty state when no groups', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    renderPage()
    expect(await screen.findByText(/no groups yet/i)).toBeInTheDocument()
  })

  it('renders groups bucketed by platform', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([
        makeGroup({ platform: 'whatsapp', name: 'WA group' }),
        makeGroup({ id: 'g2', platform: 'facebook', name: 'FB group' }),
      ]),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', { name: /whatsapp groups/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /facebook groups/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('WA group')).toBeInTheDocument()
    expect(screen.getByText('FB group')).toBeInTheDocument()
  })

  it('toggles active flag via the checkbox', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeGroup({ active: true })]))
      .mockResolvedValueOnce(jsonResponse({ ...makeGroup(), active: false }))
      .mockResolvedValueOnce(jsonResponse([{ ...makeGroup(), active: false }]))
    renderPage()

    const cb = await screen.findByRole('checkbox', {
      name: /active baka rentals wa/i,
    })
    expect(cb).toBeChecked()
    await userEvent.click(cb)

    await waitFor(() => {
      const patchCall = fetchSpy.mock.calls.find(
        ([, init]) =>
          (init as RequestInit | undefined)?.method === 'PATCH',
      )
      expect(patchCall).toBeDefined()
      expect(JSON.parse((patchCall![1] as RequestInit).body as string)).toEqual(
        { active: false },
      )
    })
  })

  it('opens the edit modal and saves changes', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeGroup({ name: 'Old name' })]))
      .mockResolvedValueOnce(jsonResponse({ ...makeGroup(), name: 'New name' }))
      .mockResolvedValueOnce(
        jsonResponse([{ ...makeGroup(), name: 'New name' }]),
      )

    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /^edit$/i }),
    )

    const nameInput = await screen.findByRole('textbox', { name: /^name/i })
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'New name')

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(screen.getByText('New name')).toBeInTheDocument()
    })
  })

  it('deletes a group after confirm', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makeGroup()]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse([]))

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /delete baka rentals wa/i }),
    )

    await waitFor(() => {
      expect(screen.queryByText('Baka Rentals WA')).not.toBeInTheDocument()
    })
  })

  it('opens the new-group modal and creates one', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([])) // initial: empty
      .mockResolvedValueOnce(jsonResponse(makeGroup({ name: 'Brand new' }), 201))
      .mockResolvedValueOnce(jsonResponse([makeGroup({ name: 'Brand new' })]))
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /new group/i }),
    )

    const nameInput = await screen.findByRole('textbox', { name: /^name/i })
    await userEvent.type(nameInput, 'Brand new')

    await userEvent.click(screen.getByRole('button', { name: /^create$/i }))

    await waitFor(() => {
      expect(screen.getByText('Brand new')).toBeInTheDocument()
    })
  })
})
