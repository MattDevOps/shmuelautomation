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

describe('ShareModal', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches the composed post and shows the English text by default', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(baseCompose))
    render(
      <ShareModal
        propertyId="p1"
        propertyLabel="Baka · ILS 8,500"
        onClose={() => {}}
      />,
    )
    expect(await screen.findByDisplayValue(/for rent — baka/i)).toBeInTheDocument()
  })

  it('switches to Hebrew when the toggle is clicked', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(baseCompose))
    render(
      <ShareModal
        propertyId="p1"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(screen.getByRole('button', { name: /עברית/i }))
    expect(screen.getByDisplayValue(/להשכרה/)).toBeInTheDocument()
  })

  it('exposes WhatsApp + Facebook share links and a copy button', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(baseCompose))
    render(
      <ShareModal
        propertyId="p1"
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
    fetchSpy.mockResolvedValueOnce(jsonResponse(baseCompose))
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    render(
      <ShareModal
        propertyId="p1"
        propertyLabel="Baka"
        onClose={() => {}}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(screen.getByRole('button', { name: /copy text/i }))
    expect(writeText).toHaveBeenCalledWith(baseCompose.text_en)
  })

  it('closes when the × button is clicked', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(baseCompose))
    const onClose = vi.fn()
    render(
      <ShareModal
        propertyId="p1"
        propertyLabel="Baka"
        onClose={onClose}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('Mark as posted invokes onMarkPosted then closes', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(baseCompose))
    const onClose = vi.fn()
    const onMarkPosted = vi.fn().mockResolvedValue(undefined)
    render(
      <ShareModal
        propertyId="p1"
        propertyLabel="Baka"
        onClose={onClose}
        onMarkPosted={onMarkPosted}
      />,
    )
    await screen.findByDisplayValue(/for rent/i)
    await userEvent.click(
      screen.getByRole('button', { name: /mark as posted/i }),
    )
    await waitFor(() => {
      expect(onMarkPosted).toHaveBeenCalled()
      expect(onClose).toHaveBeenCalled()
    })
  })
})
