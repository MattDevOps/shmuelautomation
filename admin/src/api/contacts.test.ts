import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createContact,
  exportContactsUrl,
  listContacts,
  listSegments,
} from './contacts'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('contacts API', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('listContacts encodes multiple segment filters as repeated params', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listContacts({ segment: ['buyer', 'vip'] })

    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).toMatch(/segment=buyer/)
    expect(url).toMatch(/segment=vip/)
  })

  it('listContacts omits empty filters', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listContacts({ q: '', segment: undefined })
    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).not.toContain('q=')
    expect(url).not.toContain('segment=')
  })

  it('createContact POSTs JSON', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 'c1' }, 201))
    await createContact({
      name: 'Yossi',
      phone: '+972500000000',
      email: null,
      language: 'he',
      segments: ['buyer'],
      notes: null,
      source: 'manual',
    })
    const [, init] = fetchSpy.mock.calls[0]!
    expect((init as RequestInit).method).toBe('POST')
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body).toMatchObject({ name: 'Yossi', segments: ['buyer'] })
  })

  it('listSegments returns parsed array', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(['buyer', 'renter']))
    const seg = await listSegments()
    expect(seg).toEqual(['buyer', 'renter'])
  })

  it('exportContactsUrl includes segments as repeated query params', () => {
    const url = exportContactsUrl(['buyer', 'vip'])
    expect(url).toMatch(/\/contacts\/export\.csv\?/)
    expect(url).toMatch(/segment=buyer/)
    expect(url).toMatch(/segment=vip/)
  })

  it('exportContactsUrl returns the bare endpoint for empty filter', () => {
    expect(exportContactsUrl([])).toMatch(/\/contacts\/export\.csv$/)
  })
})
