import { API_URL, request } from './client'
import type {
  Contact,
  ContactCreate,
  ContactListFilters,
  ContactUpdate,
} from './types'

function toQuery(filters: ContactListFilters): string {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  for (const s of filters.segment ?? []) {
    if (s) params.append('segment', s)
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

export function listContacts(
  filters: ContactListFilters = {},
): Promise<Contact[]> {
  return request<Contact[]>(`/contacts${toQuery(filters)}`)
}

export function getContact(id: string): Promise<Contact> {
  return request<Contact>(`/contacts/${id}`)
}

export function createContact(payload: ContactCreate): Promise<Contact> {
  return request<Contact>('/contacts', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateContact(
  id: string,
  payload: ContactUpdate,
): Promise<Contact> {
  return request<Contact>(`/contacts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteContact(id: string): Promise<void> {
  return request<void>(`/contacts/${id}`, { method: 'DELETE' })
}

export function listSegments(): Promise<string[]> {
  return request<string[]>('/contacts/segments')
}

export function exportContactsUrl(segments: string[] = []): string {
  const params = new URLSearchParams()
  for (const s of segments) {
    if (s) params.append('segment', s)
  }
  const qs = params.toString()
  return `${API_URL}/contacts/export.csv${qs ? `?${qs}` : ''}`
}
