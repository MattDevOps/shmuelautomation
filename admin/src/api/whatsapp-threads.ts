import { request } from './client'
import type {
  BotConfig,
  BotConfigUpdate,
  ThreadMode,
  WhatsappThread,
  WhatsappThreadDetail,
  WhatsappThreadList,
} from './types'

export function listThreads(params?: {
  mode?: ThreadMode
  limit?: number
  offset?: number
}): Promise<WhatsappThreadList> {
  const q = new URLSearchParams()
  if (params?.mode) q.set('mode', params.mode)
  if (params?.limit !== undefined) q.set('limit', String(params.limit))
  if (params?.offset !== undefined) q.set('offset', String(params.offset))
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return request<WhatsappThreadList>(`/whatsapp/threads${suffix}`)
}

export function getThread(
  id: string,
  params?: { message_limit?: number },
): Promise<WhatsappThreadDetail> {
  const q = new URLSearchParams()
  if (params?.message_limit !== undefined) {
    q.set('message_limit', String(params.message_limit))
  }
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return request<WhatsappThreadDetail>(`/whatsapp/threads/${id}${suffix}`)
}

export function updateThreadMode(
  id: string,
  body: { mode: ThreadMode; takeover_reason?: string | null },
): Promise<WhatsappThread> {
  return request<WhatsappThread>(`/whatsapp/threads/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function getBotConfig(): Promise<BotConfig> {
  return request<BotConfig>('/whatsapp/bot-config')
}

export function updateBotConfig(body: BotConfigUpdate): Promise<BotConfig> {
  return request<BotConfig>('/whatsapp/bot-config', {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}
