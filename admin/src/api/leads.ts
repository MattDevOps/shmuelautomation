import { request } from './client'
import type { Lead, LeadList, LeadStatus, LeadUpdate } from './types'

export function listLeads(
  params: { status?: LeadStatus; limit?: number } = {},
): Promise<LeadList> {
  const q = new URLSearchParams()
  if (params.status) q.set('status', params.status)
  if (params.limit) q.set('limit', String(params.limit))
  const qs = q.toString()
  return request<LeadList>(`/leads${qs ? `?${qs}` : ''}`)
}

export function updateLead(id: string, payload: LeadUpdate): Promise<Lead> {
  return request<Lead>(`/leads/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function approveLead(
  id: string,
): Promise<{ lead: Lead; contact_id: string }> {
  return request<{ lead: Lead; contact_id: string }>(`/leads/${id}/approve`, {
    method: 'POST',
  })
}

export function rejectLead(id: string): Promise<Lead> {
  return request<Lead>(`/leads/${id}/reject`, { method: 'POST' })
}
