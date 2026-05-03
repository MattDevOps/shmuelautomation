import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  CONNECT_GOOGLE_URL,
  deletePhoto,
  disconnectCloud,
  getCloudStatus,
  listPhotos,
  uploadPhoto,
} from './cloud'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('cloud API', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('CONNECT_GOOGLE_URL points at the start endpoint', () => {
    expect(CONNECT_GOOGLE_URL).toMatch(/\/auth\/google\/start$/)
  })

  it('getCloudStatus parses a status payload', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({
        provider: 'google_drive',
        connected: true,
        account_email: 'shmuel@example.com',
        root_folder_name: 'Classic Jerusalem Realty',
      }),
    )
    const s = await getCloudStatus()
    expect(s.connected).toBe(true)
    expect(s.account_email).toBe('shmuel@example.com')
  })

  it('disconnectCloud POSTs to disconnect', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await disconnectCloud()
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/auth\/google\/disconnect$/)
    expect((init as RequestInit).method).toBe('POST')
  })

  it('listPhotos hits per-property endpoint', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listPhotos('p1')
    expect(fetchSpy.mock.calls[0]![0]).toMatch(/\/properties\/p1\/photos$/)
  })

  it('uploadPhoto sends multipart FormData (no JSON content-type)', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 'photo1' }, 201))
    const file = new File(['hello'], 'test.jpg', { type: 'image/jpeg' })
    await uploadPhoto('p1', file)

    const [, init] = fetchSpy.mock.calls[0]!
    expect((init as RequestInit).body).toBeInstanceOf(FormData)
    const headers = new Headers((init as RequestInit).headers)
    // Critical: the browser must set its own multipart boundary header.
    expect(headers.get('content-type')).toBeNull()
  })

  it('deletePhoto sends DELETE', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await deletePhoto('p1', 'photo1')
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/properties\/p1\/photos\/photo1$/)
    expect((init as RequestInit).method).toBe('DELETE')
  })
})
