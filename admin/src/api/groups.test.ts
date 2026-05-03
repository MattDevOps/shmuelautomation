import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createGroup,
  deleteGroup,
  getGroup,
  listGroups,
  updateGroup,
} from './groups'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('groups API', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('listGroups passes platform/audience/matchesPropertyType filters', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listGroups({
      platform: 'whatsapp',
      audience: 'rent',
      matchesPropertyType: 'rent',
    })
    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).toMatch(/platform=whatsapp/)
    expect(url).toMatch(/audience=rent/)
    expect(url).toMatch(/matches_property_type=rent/)
  })

  it('listGroups defaults to active_only=true (no flag sent)', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listGroups()
    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).not.toContain('active_only')
  })

  it('listGroups({activeOnly:false}) passes the flag', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]))
    await listGroups({ activeOnly: false })
    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).toMatch(/active_only=false/)
  })

  it('createGroup POSTs the payload', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 'g1' }, 201))
    await createGroup({
      platform: 'facebook',
      audience: 'sale',
      name: 'Jerusalem Sales',
      target_url: 'https://fb.example/g',
      notes: null,
      sort_order: 0,
      active: true,
    })
    const [, init] = fetchSpy.mock.calls[0]!
    expect((init as RequestInit).method).toBe('POST')
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      platform: 'facebook',
      audience: 'sale',
      name: 'Jerusalem Sales',
    })
  })

  it('updateGroup PATCHes', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 'g1' }))
    await updateGroup('g1', { name: 'New name' })
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/groups\/g1$/)
    expect((init as RequestInit).method).toBe('PATCH')
  })

  it('deleteGroup DELETEs', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await deleteGroup('g1')
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/groups\/g1$/)
    expect((init as RequestInit).method).toBe('DELETE')
  })

  it('getGroup fetches by id', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 'g1' }))
    await getGroup('g1')
    expect(fetchSpy.mock.calls[0]![0]).toMatch(/\/groups\/g1$/)
  })
})
