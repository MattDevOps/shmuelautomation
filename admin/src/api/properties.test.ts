import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createProperty,
  deleteProperty,
  getProperty,
  listProperties,
  updateProperty,
} from './properties'
import type { Property, PropertyCreate } from './types'
import { ApiError } from './client'

const samplePayload: PropertyCreate = {
  type: 'rent',
  status: 'available',
  price: '8500.00',
  currency: 'ILS',
  rooms: '3.5',
  size_sqm: 80,
  floor: null,
  address: null,
  neighborhood: 'Baka',
  city: 'Jerusalem',
  owner_name: 'Yossi',
  owner_phone: '+972500000000',
  broker_fee_status: 'yes',
  broker_fee_amount: null,
  description: null,
  notes: null,
  yad2_url: null,
}

const sampleProperty: Property = {
  id: 'p1',
  ...samplePayload,
  created_at: '2026-05-03T00:00:00',
  updated_at: '2026-05-03T00:00:00',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('properties API', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('listProperties sends only set filters as query params', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([sampleProperty]))
    await listProperties({ type: 'rent', status: undefined, q: '' })

    const url = fetchSpy.mock.calls[0]![0] as string
    expect(url).toMatch(/\/properties\?type=rent$/)
    expect(url).not.toContain('status=')
    expect(url).not.toContain('q=')
  })

  it('listProperties returns parsed array', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([sampleProperty]))
    const result = await listProperties()
    expect(result).toHaveLength(1)
    expect(result[0]!.id).toBe('p1')
  })

  it('createProperty POSTs JSON', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(sampleProperty, 201))
    await createProperty(samplePayload)

    const [, init] = fetchSpy.mock.calls[0]!
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toMatchObject({
      type: 'rent',
      neighborhood: 'Baka',
    })
    expect(new Headers(init?.headers).get('content-type')).toBe(
      'application/json',
    )
  })

  it('updateProperty PATCHes partial payload', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(sampleProperty))
    await updateProperty('p1', { status: 'rented' })

    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toMatch(/\/properties\/p1$/)
    expect(init?.method).toBe('PATCH')
    expect(JSON.parse(init?.body as string)).toEqual({ status: 'rented' })
  })

  it('getProperty fetches by id', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(sampleProperty))
    await getProperty('p1')
    expect(fetchSpy.mock.calls[0]![0]).toMatch(/\/properties\/p1$/)
  })

  it('deleteProperty handles 204 No Content', async () => {
    fetchSpy.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(deleteProperty('p1')).resolves.toBeUndefined()
  })

  it('throws ApiError on 4xx with detail', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ detail: 'property not found' }, 404),
    )
    await expect(getProperty('missing')).rejects.toBeInstanceOf(ApiError)
  })
})
