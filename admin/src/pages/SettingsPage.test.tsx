import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import SettingsPage from './SettingsPage'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function renderPage(initialEntry = '/settings') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <SettingsPage />
    </MemoryRouter>,
  )
}

describe('SettingsPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows Connect Google Drive when not connected', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        provider: 'google_drive',
        connected: false,
        account_email: null,
        root_folder_name: null,
      }),
    )
    renderPage()

    const link = await screen.findByRole('link', { name: /connect google drive/i })
    expect(link.getAttribute('href')).toMatch(/\/auth\/google\/start$/)
  })

  it('shows account info + Disconnect when connected', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        provider: 'google_drive',
        connected: true,
        account_email: 'shmuel@example.com',
        root_folder_name: 'Classic Jerusalem Realty',
      }),
    )
    renderPage()

    expect(await screen.findByText(/shmuel@example\.com/)).toBeInTheDocument()
    expect(screen.getByText(/classic jerusalem realty/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /disconnect google drive/i }),
    ).toBeInTheDocument()
  })

  it('disconnects after confirm and updates status', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          provider: 'google_drive',
          connected: true,
          account_email: 'shmuel@example.com',
          root_folder_name: 'X',
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /disconnect google drive/i }),
    )

    await waitFor(() => {
      expect(
        screen.getByRole('link', { name: /connect google drive/i }),
      ).toBeInTheDocument()
    })
  })

  it('shows success flash when redirected with cloud_connected', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        provider: 'google_drive',
        connected: true,
        account_email: 'a@b',
        root_folder_name: 'X',
      }),
    )
    renderPage('/settings?cloud_connected=1')
    expect(await screen.findByRole('status')).toHaveTextContent(
      /google drive connected/i,
    )
  })

  it('shows error flash when redirected with cloud_error', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        provider: 'google_drive',
        connected: false,
        account_email: null,
        root_folder_name: null,
      }),
    )
    renderPage('/settings?cloud_error=access_denied')
    expect(await screen.findByRole('alert')).toHaveTextContent(/access_denied/i)
  })
})
