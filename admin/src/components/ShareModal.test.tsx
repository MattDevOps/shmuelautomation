import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShareModal from './ShareModal'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const baseCompose = {
  text_en: 'For rent — Baka\nILS 8,500',
  text_he: 'להשכרה בBaka\nILS 8,500',
  whatsapp_share_url: 'https://wa.me/?text=For%20rent',
  facebook_share_url: 'https://www.facebook.com/sharer/sharer.php?u=https',
}

function setupFetch(
  fetchSpy: ReturnType<typeof vi.spyOn>,
  opts: {
    compose?: typeof baseCompose
    groups?: Array<Record<string, unknown>>
  } = {},
): void {
  // The modal fires composePropertyPost + listGroups in parallel; route by URL.
  fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/groups')) return jsonResponse(opts.groups ?? [])
    return jsonResponse(opts.compose ?? baseCompose)
  })
}

describe('ShareModal', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches the composed post and shows the English text by default', async () => {
    setupFetch(fetchSpy)
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka · ILS 8,500"
        onClose={() => {}}
      />,
    )
    expect(await screen.findByDisplayValue(/for rent — baka/i)).toBeInTheDocument()
  })

  it('switches to Hebrew when the toggle is clicked', async () => {
    setupFetch(fetchSpy)
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(screen.getByRole('button', { name: /עברית/i }))
    expect(screen.getByDisplayValue(/להשכרה/)).toBeInTheDocument()
  })

  it('exposes WhatsApp + Facebook share links and a copy button', async () => {
    setupFetch(fetchSpy)
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    expect(
      screen.getByRole('link', { name: /open whatsapp/i }).getAttribute('href'),
    ).toContain('wa.me')
    expect(
      screen.getByRole('link', { name: /share to facebook/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy text/i })).toBeInTheDocument()
  })

  it('copies the displayed text to the clipboard', async () => {
    setupFetch(fetchSpy)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(screen.getByRole('button', { name: /copy text/i }))
    expect(writeText).toHaveBeenCalledWith(baseCompose.text_en)
  })

  it('closes when the × button is clicked', async () => {
    setupFetch(fetchSpy)
    const onClose = vi.fn()
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={onClose}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('Mark as posted invokes onMarkPosted then closes', async () => {
    setupFetch(fetchSpy)
    const onClose = vi.fn()
    const onMarkPosted = vi.fn().mockResolvedValue(undefined)
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={onClose}
        onMarkPosted={onMarkPosted}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(
      screen.getByRole('button', { name: /mark slot as posted/i }),
    )
    await waitFor(() => {
      expect(onMarkPosted).toHaveBeenCalled()
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('renders matching groups grouped by platform with checkboxes', async () => {
    setupFetch(fetchSpy, {
      groups: [
        {
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
        },
        {
          id: 'g2',
          platform: 'facebook',
          audience: 'both',
          name: 'Jerusalem Real Estate',
          target_url: null,
          notes: null,
          sort_order: 0,
          active: true,
          created_at: '2026-05-03T00:00:00',
          updated_at: '2026-05-03T00:00:00',
        },
      ],
    })
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    expect(
      await screen.findByRole('checkbox', { name: /baka rentals wa/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: /jerusalem real estate/i }),
    ).toBeInTheDocument()
    // Group jump-link rendered when target_url present
    expect(
      screen.getByRole('link', { name: /open ↗/ }).getAttribute('href'),
    ).toBe('https://chat.whatsapp.com/abc')
  })

  it('toggles a group as posted when its checkbox is clicked', async () => {
    setupFetch(fetchSpy, {
      groups: [
        {
          id: 'g1',
          platform: 'whatsapp',
          audience: 'rent',
          name: 'Baka Rentals WA',
          target_url: null,
          notes: null,
          sort_order: 0,
          active: true,
          created_at: '2026-05-03T00:00:00',
          updated_at: '2026-05-03T00:00:00',
        },
      ],
    })
    render(
      <ShareModal
        propertyId="p1"
        propertyType="rent"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    const cb = await screen.findByRole('checkbox', { name: /baka rentals wa/i })
    expect(cb).not.toBeChecked()
    await userEvent.click(cb)
    expect(cb).toBeChecked()
    await userEvent.click(cb)
    expect(cb).not.toBeChecked()
  })
})
