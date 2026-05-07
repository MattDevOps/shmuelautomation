import { request } from './client'

export type SubscriberPreference = 'rent' | 'sale' | 'both'

export interface NewsletterSubscriber {
  id: string
  email: string
  language: string
  type_filter: SubscriberPreference
  confirmed_at: string | null
  unsubscribed_at: string | null
  last_digest_at: string | null
  source: string | null
  created_at: string
}

export interface SubscriberStats {
  total: number
  confirmed: number
  pending: number
  unsubscribed: number
}

export interface SubscriberListResponse {
  items: NewsletterSubscriber[]
  stats: SubscriberStats
}

export function listSubscribers(): Promise<SubscriberListResponse> {
  return request<SubscriberListResponse>('/newsletter/subscribers')
}

export function deleteSubscriber(id: string): Promise<void> {
  return request<void>(`/newsletter/subscribers/${id}`, { method: 'DELETE' })
}
