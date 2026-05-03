import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import PhotoSection from './PhotoSection'
import type { CloudPhoto } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makePhoto(overrides: Partial<CloudPhoto> = {}): CloudPhoto {
  return {
    id: 'ph1',
    property_id: 'p1',
    provider: 'google_drive',
    external_id: 'drive-1',
    folder_external_id: 'folder-1',
    file_name: 'front.jpg',
    mime_type: 'image/jpeg',
    size_bytes: 1234,
    web_view_url: 'https://drive.google.com/file/d/drive-1/view',
    thumbnail_url: 'https://lh3.googleusercontent.com/t/drive-1',
    created_at: '2026-05-03T00:00:00',
    ...overrides,
  }
}

function renderSection() {
  return render(
    <MemoryRouter>
      <PhotoSection propertyId="p1" />
    </MemoryRouter>,
  )
}

describe('PhotoSection', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders existing photos as a grid', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse([makePhoto(), makePhoto({ id: 'ph2', file_name: 'back.jpg' })]),
    )
    renderSection()

    expect(await screen.findByAltText('front.jpg')).toBeInTheDocument()
    expect(screen.getByAltText('back.jpg')).toBeInTheDocument()
  })

  it('shows empty state when no photos', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    renderSection()
    expect(await screen.findByText(/no photos yet/i)).toBeInTheDocument()
  })

  it('uploads a chosen file and adds it to the grid', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse(makePhoto({ file_name: 'new.jpg' }), 201),
      )
    renderSection()
    await screen.findByText(/no photos yet/i)

    const file = new File(['x'], 'new.jpg', { type: 'image/jpeg' })
    await userEvent.upload(screen.getByLabelText(/upload photos/i), file)

    expect(await screen.findByAltText('new.jpg')).toBeInTheDocument()
    const uploadCall = fetchSpy.mock.calls.find(
      ([, init]) =>
        (init as RequestInit | undefined)?.method === 'POST' &&
        (init as RequestInit | undefined)?.body instanceof FormData,
    )
    expect(uploadCall).toBeDefined()
  })

  it('surfaces 412 with a "connect Drive" banner', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'Google Drive is not connected.' }, 412),
      )
    renderSection()
    await screen.findByText(/no photos yet/i)

    const file = new File(['x'], 'new.jpg', { type: 'image/jpeg' })
    await userEvent.upload(screen.getByLabelText(/upload photos/i), file)

    expect(
      await screen.findByRole('link', { name: /connect it in settings/i }),
    ).toBeInTheDocument()
    const alerts = screen.getAllByRole('alert')
    expect(
      alerts.some((el) => /google drive is not connected/i.test(el.textContent ?? '')),
    ).toBe(true)
  })

  it('deletes a photo optimistically and rolls back on failure', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse([makePhoto({ file_name: 'front.jpg' })]),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: 'boom' }, 500))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection()

    await userEvent.click(
      await screen.findByRole('button', { name: /delete front\.jpg/i }),
    )
    // Rollback path: photo reappears after the delete request fails.
    await waitFor(() => {
      expect(screen.getByAltText('front.jpg')).toBeInTheDocument()
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(/500/)
  })

  it('deletes successfully when backend accepts', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse([makePhoto({ file_name: 'front.jpg' })]),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection()

    await userEvent.click(
      await screen.findByRole('button', { name: /delete front\.jpg/i }),
    )
    await waitFor(() => {
      expect(screen.queryByAltText('front.jpg')).not.toBeInTheDocument()
    })
  })
})
