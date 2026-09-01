import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ContentPage from './ContentPage'
import type { BlogPost, NeighborhoodContent, SitePage } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makePost(overrides: Partial<BlogPost> = {}): BlogPost {
  return {
    id: 'b1',
    slug: 'a-day-in-baka',
    title: 'A Day in Baka',
    content_html: '<p>hello</p>',
    excerpt_html: null,
    image_url: null,
    published_at: '2024-07-23T20:56:31',
    published: true,
    wp_id: 101,
    created_at: '2026-09-01T00:00:00',
    updated_at: '2026-09-01T00:00:00',
    ...overrides,
  }
}

function makeNeighborhood(
  overrides: Partial<NeighborhoodContent> = {},
): NeighborhoodContent {
  return {
    id: 'n1',
    slug: 'rehavia',
    title: 'Rehavia',
    content_html: '<p>leafy</p>',
    card_image_url: null,
    hero_image_url: null,
    sort_order: 2,
    published: true,
    wp_id: 55,
    created_at: '2026-09-01T00:00:00',
    updated_at: '2026-09-01T00:00:00',
    ...overrides,
  }
}

function makePage(overrides: Partial<SitePage> = {}): SitePage {
  return {
    id: 'p1',
    slug: 'contact',
    title: 'Contact',
    content_html: '<p>reach us</p>',
    data: { contact_data: { phone_number: '02-123' } },
    published: true,
    wp_id: 742,
    created_at: '2026-09-01T00:00:00',
    updated_at: '2026-09-01T00:00:00',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ContentPage />
    </MemoryRouter>,
  )
}

describe('ContentPage', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('warns that this content is not live yet', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([makePost()]))
    renderPage()
    expect(
      await screen.findByText(/still shows the WordPress versions/i),
    ).toBeInTheDocument()
  })

  it('lists blog posts and marks drafts', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse([makePost(), makePost({ id: 'b2', title: 'Draft one', published: false })]),
    )
    renderPage()

    expect(await screen.findByText('A Day in Baka')).toBeInTheDocument()
    expect(screen.getByText('Draft one')).toBeInTheDocument()
    expect(screen.getByText('Draft')).toBeInTheDocument()
  })

  it('creating a post posts to the blog endpoint', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(makePost(), 201))
      .mockResolvedValue(jsonResponse([makePost()]))

    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /new post/i }))
    await userEvent.type(screen.getByLabelText(/^Title$/i), 'A Day in Baka')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      const posted = fetchSpy.mock.calls.find(
        (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
      )
      expect(String(posted?.[0])).toContain('/content/blog')
    })
  })

  it('switches to neighbourhoods and shows their order', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makePost()]))
      .mockResolvedValue(jsonResponse([makeNeighborhood()]))

    renderPage()
    await screen.findByText('A Day in Baka')
    await userEvent.click(screen.getByRole('button', { name: /neighbourhoods/i }))

    expect(await screen.findByText('Rehavia')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('page addresses are shown as fixed, not editable', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResponse([makePost()]))
      .mockResolvedValue(jsonResponse([makePage()]))

    renderPage()
    await screen.findByText('A Day in Baka')
    await userEvent.click(screen.getByRole('button', { name: /^pages$/i }))

    await screen.findByText('Contact')
    await userEvent.click(screen.getByRole('button', { name: /edit/i }))
    expect(await screen.findByText(/fixed, because the site links to it/i)).toBeInTheDocument()
  })
})
