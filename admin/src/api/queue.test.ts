import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cancelSlot,
  composePropertyPost,
  listQueue,
  markPosted,
  skipSlot,
} from './queue'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('queue API', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('listQueue passes due_only when set', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listQueue({ dueOnly: true, limit: 25 })
    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).toMatch(/\/post-queue\?/)
    expect(url).toMatch(/due_only=true/)
    expect(url).toMatch(/limit=25/)
  })

  it('listQueue without options hits the bare endpoint', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listQueue()
    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).toMatch(/\/post-queue$/)
  })

  it('markPosted PATCHes /:id/posted', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 's1', status: 'posted' }))
    await markPosted('s1')
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/post-queue\/s1\/posted$/)
    expect((init as RequestInit).method).toBe('PATCH')
  })

  it('skipSlot PATCHes /:id/skip', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 's1', status: 'skipped' }))
    await skipSlot('s1')
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/post-queue\/s1\/skip$/)
    expect((init as RequestInit).method).toBe('PATCH')
  })

  it('cancelSlot DELETEs', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await cancelSlot('s1')
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/post-queue\/s1$/)
    expect((init as RequestInit).method).toBe('DELETE')
  })

  it('composePropertyPost GETs /properties/:id/compose', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        text_en: 'For rent',
        text_he: 'להשכרה',
        whatsapp_share_url: 'https://wa.me/?text=For%20rent',
        facebook_share_url: null,
      }),
    )
    const result = await composePropertyPost('p1')
    expect(fetchSpy.mock.calls[0]![0]).toMatch(/\/properties\/p1\/compose$/)
    expect(result.text_he).toBe('להשכרה')
  })
})
