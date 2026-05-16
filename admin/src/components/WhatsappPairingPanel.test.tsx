import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WhatsappPairingPanel from './WhatsappPairingPanel'
import type { WhatsappStatus } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const UNCONFIGURED: WhatsappStatus = {
  configured: false,
  reachable: false,
  connection_state: null,
  paired_phone: null,
  last_connected_at: null,
  last_disconnect_reason: null,
}

const CONNECTED: WhatsappStatus = {
  configured: true,
  reachable: true,
  connection_state: 'connected',
  paired_phone: '972527485568',
  last_connected_at: '2026-05-16T10:00:00Z',
  last_disconnect_reason: null,
}

const PAIRING: WhatsappStatus = {
  configured: true,
  reachable: true,
  connection_state: 'pairing',
  paired_phone: null,
  last_connected_at: null,
  last_disconnect_reason: null,
}

// Route fetch by URL so we can mix status + qr responses across one test.
function routeFetch(
  fetchSpy: ReturnType<typeof vi.spyOn>,
  handlers: { status?: WhatsappStatus; qrPng?: string | null },
): void {
  fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/whatsapp/qr')) {
      return jsonResponse({ qrPng: handlers.qrPng ?? null })
    }
    return jsonResponse(handlers.status ?? UNCONFIGURED)
  })
}

describe('WhatsappPairingPanel', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the not-configured state when WHATSAPP_DAEMON_URL is unset', async () => {
    routeFetch(fetchSpy, { status: UNCONFIGURED })
    render(<WhatsappPairingPanel />)
    expect(
      await screen.findByText(/WhatsApp daemon — not configured/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/WHATSAPP_DAEMON_URL/)).toBeInTheDocument()
  })

  it('shows the unreachable state when the daemon does not respond', async () => {
    routeFetch(fetchSpy, {
      status: { ...UNCONFIGURED, configured: true },
    })
    render(<WhatsappPairingPanel />)
    expect(
      await screen.findByText(/WhatsApp daemon — unreachable/i),
    ).toBeInTheDocument()
  })

  it('shows the connected state with the paired phone number', async () => {
    routeFetch(fetchSpy, { status: CONNECTED })
    render(<WhatsappPairingPanel />)
    expect(
      await screen.findByText(/WhatsApp daemon — connected/i),
    ).toBeInTheDocument()
    expect(screen.getByText('972527485568')).toBeInTheDocument()
    // No QR fetch when already connected.
    const qrCalls = fetchSpy.mock.calls.filter(([input]) =>
      (typeof input === 'string' ? input : String(input)).includes('/whatsapp/qr'),
    )
    expect(qrCalls).toHaveLength(0)
  })

  it('shows the QR code while waiting for pairing', async () => {
    routeFetch(fetchSpy, {
      status: PAIRING,
      qrPng: 'data:image/png;base64,QRDATA',
    })
    render(<WhatsappPairingPanel />)
    await waitFor(() => {
      expect(
        screen.getByText(/WhatsApp daemon — waiting for pairing/i),
      ).toBeInTheDocument()
    })
    const img = await screen.findByAltText(/WhatsApp pairing QR code/i)
    expect(img.getAttribute('src')).toBe('data:image/png;base64,QRDATA')
  })

  it('shows "waiting for QR" copy when daemon has none yet', async () => {
    routeFetch(fetchSpy, { status: PAIRING, qrPng: null })
    render(<WhatsappPairingPanel />)
    expect(
      await screen.findByText(/Waiting for the daemon to produce a QR/i),
    ).toBeInTheDocument()
  })

  it('posts /whatsapp/reset after confirm', async () => {
    routeFetch(fetchSpy, { status: CONNECTED })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<WhatsappPairingPanel />)

    const btn = await screen.findByRole('button', { name: /reset & re-pair/i })

    // Once the reset call has fired, mock the next status fetch as PAIRING.
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/whatsapp/reset')) return jsonResponse({ ok: true })
      if (url.includes('/whatsapp/qr')) return jsonResponse({ qrPng: null })
      return jsonResponse(PAIRING)
    })

    await userEvent.click(btn)

    await waitFor(() => {
      const resetCalls = fetchSpy.mock.calls.filter(([input, init]) => {
        const url = typeof input === 'string' ? input : String(input)
        return url.includes('/whatsapp/reset') && init?.method === 'POST'
      })
      expect(resetCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('does not call /whatsapp/reset when confirm is dismissed', async () => {
    routeFetch(fetchSpy, { status: CONNECTED })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<WhatsappPairingPanel />)

    const btn = await screen.findByRole('button', { name: /reset & re-pair/i })
    await userEvent.click(btn)

    const resetCalls = fetchSpy.mock.calls.filter(([input]) =>
      (typeof input === 'string' ? input : String(input)).includes('/whatsapp/reset'),
    )
    expect(resetCalls).toHaveLength(0)
  })
})
