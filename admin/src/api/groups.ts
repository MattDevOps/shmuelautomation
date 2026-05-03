import { request } from './client'
import type {
  Group,
  GroupAudience,
  GroupCreate,
  GroupPlatform,
  GroupUpdate,
} from './types'

interface GroupListFilters {
  platform?: GroupPlatform
  audience?: GroupAudience
  matchesPropertyType?: 'rent' | 'sale'
  activeOnly?: boolean
}

export function listGroups(filters: GroupListFilters = {}): Promise<Group[]> {
  const params = new URLSearchParams()
  if (filters.platform) params.set('platform', filters.platform)
  if (filters.audience) params.set('audience', filters.audience)
  if (filters.matchesPropertyType)
    params.set('matches_property_type', filters.matchesPropertyType)
  if (filters.activeOnly === false) params.set('active_only', 'false')
  const qs = params.toString()
  return request<Group[]>(`/groups${qs ? `?${qs}` : ''}`)
}

export function getGroup(id: string): Promise<Group> {
  return request<Group>(`/groups/${id}`)
}

export function createGroup(payload: GroupCreate): Promise<Group> {
  return request<Group>('/groups', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateGroup(id: string, payload: GroupUpdate): Promise<Group> {
  return request<Group>(`/groups/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteGroup(id: string): Promise<void> {
  return request<void>(`/groups/${id}`, { method: 'DELETE' })
}
