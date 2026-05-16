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

const WHATSAPP_UNCONFIGURED = {
  configured: false,
  reachable: false,
  connection_state: null,
  paired_phone: null,
  last_connected_at: null,
  last_disconnect_reason: null,
}

// SettingsPage now mounts both the cloud-status panel and the WhatsApp
// pairing panel, each with their own fetch. Route by URL so test order
// of arrival doesn't matter.
function routeFetch(
  fetchSpy: ReturnType<typeof vi.spyOn>,
  cloudBody: unknown,
  disconnectBody: Response | null = null,
): void {
  let disconnected = false
  fetchSpy.mockImplementation(async (input: RequestInfo | URL, init) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/whatsapp/qr')) {
      return jsonResponse({ qrPng: null })
    }
    if (url.includes('/whatsapp/status')) {
      return jsonResponse(WHATSAPP_UNCONFIGURED)
    }
    if (url.includes('/auth/google/disconnect') && init?.method === 'POST') {
      disconnected = true
      return disconnectBody ?? new Response(null, { status: 204 })
    }
    // /auth/google/status — flip to disconnected once /disconnect ran.
    if (disconnected) {
      return jsonResponse({
        provider: 'google_drive',
        connected: false,
        account_email: null,
        root_folder_name: null,
      })
    }
    return jsonResponse(cloudBody)
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
    routeFetch(fetchSpy, {
      provider: 'google_drive',
      connected: false,
      account_email: null,
      root_folder_name: null,
    })
    renderPage()

    const link = await screen.findByRole('link', { name: /connect google drive/i })
    expect(link.getAttribute('href')).toMatch(/\/auth\/google\/start$/)
  })

  it('shows account info + Disconnect when connected', async () => {
    routeFetch(fetchSpy, {
      provider: 'google_drive',
      connected: true,
      account_email: 'shmuel@example.com',
      root_folder_name: 'Classic Jerusalem Realty',
    })
    renderPage()

    expect(await screen.findByText(/shmuel@example\.com/)).toBeInTheDocument()
    expect(screen.getByText(/classic jerusalem realty/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /disconnect google drive/i }),
    ).toBeInTheDocument()
  })

  it('disconnects after confirm and updates status', async () => {
    routeFetch(fetchSpy, {
      provider: 'google_drive',
      connected: true,
      account_email: 'shmuel@example.com',
      root_folder_name: 'X',
    })
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
    routeFetch(fetchSpy, {
      provider: 'google_drive',
      connected: true,
      account_email: 'a@b',
      root_folder_name: 'X',
    })
    renderPage('/settings?cloud_connected=1')
    expect(await screen.findByRole('status')).toHaveTextContent(
      /google drive connected/i,
    )
  })

  it('shows error flash when redirected with cloud_error', async () => {
    routeFetch(fetchSpy, {
      provider: 'google_drive',
      connected: false,
      account_email: null,
      root_folder_name: null,
    })
    renderPage('/settings?cloud_error=access_denied')
    expect(await screen.findByRole('alert')).toHaveTextContent(/access_denied/i)
  })
})
