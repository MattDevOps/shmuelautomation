import { API_URL, request } from './client'
import type {
  BulkResult,
  ContactMatch,
  DuplicateMatch,
  Property,
  PropertyCreate,
  PropertyListFilters,
  PropertyNote,
  PropertyStatus,
  PropertyUpdate,
  Yad2ImportPreview,
} from './types'

export const EXPORT_URL = `${API_URL}/properties/export`

function toQuery(filters: PropertyListFilters): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === '' || v === null) continue
    params.set(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

export function listProperties(
  filters: PropertyListFilters = {},
): Promise<Property[]> {
  return request<Property[]>(`/properties${toQuery(filters)}`)
}

export function getProperty(id: string): Promise<Property> {
  return request<Property>(`/properties/${id}`)
}

export function createProperty(payload: PropertyCreate): Promise<Property> {
  return request<Property>('/properties', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateProperty(
  id: string,
  payload: PropertyUpdate,
): Promise<Property> {
  return request<Property>(`/properties/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteProperty(id: string): Promise<void> {
  return request<void>(`/properties/${id}`, { method: 'DELETE' })
}

export function importFromYad2(url: string): Promise<Yad2ImportPreview> {
  return request<Yad2ImportPreview>('/properties/import/yad2', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export function listMatchingContacts(
  propertyId: string,
): Promise<ContactMatch[]> {
  return request<ContactMatch[]>(
    `/properties/${propertyId}/matching-contacts`,
  )
}

export function findDuplicateProperties(
  neighborhood: string,
  address: string,
  excludeId?: string,
): Promise<DuplicateMatch[]> {
  const params = new URLSearchParams({ neighborhood, address })
  if (excludeId) params.set('exclude_id', excludeId)
  return request<DuplicateMatch[]>(`/properties/duplicates?${params.toString()}`)
}

export function bulkUpdateStatus(
  ids: string[],
  status: PropertyStatus,
): Promise<BulkResult> {
  return request<BulkResult>('/properties/bulk/status', {
    method: 'POST',
    body: JSON.stringify({ ids, status }),
  })
}

export function bulkDeleteProperties(ids: string[]): Promise<BulkResult> {
  return request<BulkResult>('/properties/bulk/delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  })
}

export function listPropertyNotes(
  propertyId: string,
): Promise<PropertyNote[]> {
  return request<PropertyNote[]>(`/properties/${propertyId}/notes`)
}

export function createPropertyNote(
  propertyId: string,
  body: string,
): Promise<PropertyNote> {
  return request<PropertyNote>(`/properties/${propertyId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function deletePropertyNote(
  propertyId: string,
  noteId: string,
): Promise<void> {
  return request<void>(`/properties/${propertyId}/notes/${noteId}`, {
    method: 'DELETE',
  })
}
