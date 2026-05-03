import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ImportYad2Page from './ImportYad2Page'
import type { Yad2ImportPreview } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/import']}>
      <Routes>
        <Route path="/import" element={<ImportYad2Page />} />
        <Route path="/" element={<div data-testid="home">home</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ImportYad2Page', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches a preview and pre-fills the form', async () => {
    const preview: Yad2ImportPreview = {
      url: 'https://www.yad2.co.il/x',
      title: 'דירה בבקעה',
      description: 'desc',
      price: '3200000',
      rooms: '4',
      size_sqm: 95,
      floor: null,
      address: 'Emek Refaim 12',
      neighborhood: 'Baka',
      image_urls: ['https://img.yad2.co.il/p1.jpg'],
      warnings: [],
    }
    fetchSpy.mockResolvedValueOnce(jsonResponse(preview))

    renderPage()
    await userEvent.type(
      screen.getByRole('textbox', { name: /yad2 url/i }),
      'https://www.yad2.co.il/x',
    )
    await userEvent.click(screen.getByRole('button', { name: /^fetch$/i }))

    await screen.findByRole('heading', { name: /review and save/i })
    expect(screen.getByRole('spinbutton', { name: /^price$/i })).toHaveValue(
      3200000,
    )
    expect(screen.getByRole('textbox', { name: /^neighborhood$/i })).toHaveValue(
      'Baka',
    )
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://img.yad2.co.il/p1.jpg',
    )
  })

  it('shows warnings from the backend', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        url: 'https://www.yad2.co.il/x',
        title: null,
        description: null,
        price: null,
        rooms: null,
        size_sqm: null,
        floor: null,
        address: null,
        neighborhood: null,
        image_urls: [],
        warnings: ['Could not load the page (timeout). Fill in manually.'],
      } satisfies Yad2ImportPreview),
    )

    renderPage()
    await userEvent.type(
      screen.getByRole('textbox', { name: /yad2 url/i }),
      'https://www.yad2.co.il/x',
    )
    await userEvent.click(screen.getByRole('button', { name: /^fetch$/i }))

    await screen.findByRole('status')
    expect(screen.getByRole('status')).toHaveTextContent(/could not load/i)
    // Form still opens so the user can fill in manually
    expect(
      screen.getByRole('heading', { name: /review and save/i }),
    ).toBeInTheDocument()
  })

  it('surfaces backend errors (e.g. non-yad2 URL)', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ detail: 'Not a yad2.co.il URL' }, 400),
    )

    renderPage()
    await userEvent.type(
      screen.getByRole('textbox', { name: /yad2 url/i }),
      'https://www.yad2.co.il/x',
    )
    await userEvent.click(screen.getByRole('button', { name: /^fetch$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/400/)
    expect(
      screen.queryByRole('heading', { name: /review and save/i }),
    ).not.toBeInTheDocument()
  })

  it('saves via createProperty and navigates home', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          url: 'https://www.yad2.co.il/x',
          title: 't',
          description: null,
          price: '3200000',
          rooms: null,
          size_sqm: null,
          floor: null,
          address: null,
          neighborhood: null,
          image_urls: [],
          warnings: [],
        } satisfies Yad2ImportPreview),
      )
      .mockResolvedValueOnce(jsonResponse({ id: 'p1' }, 201))

    renderPage()
    await userEvent.type(
      screen.getByRole('textbox', { name: /yad2 url/i }),
      'https://www.yad2.co.il/x',
    )
    await userEvent.click(screen.getByRole('button', { name: /^fetch$/i }))
    await screen.findByRole('heading', { name: /review and save/i })
    await userEvent.click(
      screen.getByRole('button', { name: /create property/i }),
    )

    await waitFor(() => {
      const lastCall = fetchSpy.mock.calls.at(-1)
      const init = lastCall?.[1] as RequestInit | undefined
      expect(init?.method).toBe('POST')
      expect(JSON.parse(init?.body as string)).toMatchObject({
        yad2_url: 'https://www.yad2.co.il/x',
        price: '3200000',
      })
    })
    await screen.findByTestId('home')
  })
})
