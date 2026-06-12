import { request } from './client'
import type { DispatchResult, PostCompose, PostSlotWithProperty } from './types'

export function listQueue(opts: {
  dueOnly?: boolean
  limit?: number
} = {}): Promise<PostSlotWithProperty[]> {
  const params = new URLSearchParams()
  if (opts.dueOnly) params.set('due_only', 'true')
  if (opts.limit !== undefined) params.set('limit', String(opts.limit))
  const qs = params.toString()
  return request<PostSlotWithProperty[]>(`/post-queue${qs ? `?${qs}` : ''}`)
}

export function markPosted(slotId: string): Promise<PostSlotWithProperty> {
  return request<PostSlotWithProperty>(`/post-queue/${slotId}/posted`, {
    method: 'PATCH',
  })
}

export function skipSlot(slotId: string): Promise<PostSlotWithProperty> {
  return request<PostSlotWithProperty>(`/post-queue/${slotId}/skip`, {
    method: 'PATCH',
  })
}

export function cancelSlot(slotId: string): Promise<void> {
  return request<void>(`/post-queue/${slotId}`, { method: 'DELETE' })
}

export function dispatchNow(slotId: string): Promise<DispatchResult> {
  return request<DispatchResult>(`/post-queue/${slotId}/dispatch`, {
    method: 'POST',
  })
}

export function composePropertyPost(propertyId: string): Promise<PostCompose> {
  return request<PostCompose>(`/properties/${propertyId}/compose`)
}
