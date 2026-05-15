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

export interface PreviewOptions {
  language?: 'en' | 'he'
  type_filter?: SubscriberPreference
  limit?: number
}

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

/**
 * Fetch the rendered digest HTML for the admin preview modal. Routes
 * through fetch directly (not the `request()` JSON helper) because the
 * endpoint returns text/html, but still attaches X-API-Key.
 */
export async function previewDigestHtml(opts: PreviewOptions = {}): Promise<string> {
  const params = new URLSearchParams()
  if (opts.language) params.set('language', opts.language)
  if (opts.type_filter) params.set('type_filter', opts.type_filter)
  if (opts.limit) params.set('limit', String(opts.limit))
  const qs = params.toString() ? `?${params.toString()}` : ''
  const headers: Record<string, string> = {}
  if (API_KEY) headers['x-api-key'] = API_KEY
  const r = await fetch(`${API_URL}/newsletter/preview${qs}`, { headers })
  if (!r.ok) throw new Error(`Preview failed: ${r.status}`)
  return r.text()
}
