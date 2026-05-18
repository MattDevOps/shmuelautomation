import { request } from './client'
import type {
  ConversationSummary,
  ConversationSummaryList,
  SummarizeRunResult,
} from './types'

export function listSummaries(params?: {
  contact_id?: string
  chat_jid?: string
  limit?: number
  offset?: number
}): Promise<ConversationSummaryList> {
  const q = new URLSearchParams()
  if (params?.contact_id) q.set('contact_id', params.contact_id)
  if (params?.chat_jid) q.set('chat_jid', params.chat_jid)
  if (params?.limit !== undefined) q.set('limit', String(params.limit))
  if (params?.offset !== undefined) q.set('offset', String(params.offset))
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return request<ConversationSummaryList>(`/whatsapp/summaries${suffix}`)
}

export function listThreadSummaries(
  threadId: string,
): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>(
    `/whatsapp/threads/${threadId}/summaries`,
  )
}

export function runSummarizeAll(): Promise<SummarizeRunResult> {
  return request<SummarizeRunResult>('/whatsapp/summaries/run', {
    method: 'POST',
  })
}

export function summarizeThread(
  threadId: string,
): Promise<SummarizeRunResult['threads'][number]> {
  return request(`/whatsapp/threads/${threadId}/summarize`, {
    method: 'POST',
  })
}

export function sendDailyDigest(): Promise<{ sent: boolean; reason?: string }> {
  return request('/whatsapp/summaries/send-digest', { method: 'POST' })
}
