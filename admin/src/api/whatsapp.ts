import { request } from './client'
import type { WhatsappQr, WhatsappStatus } from './types'

export function getWhatsappStatus(): Promise<WhatsappStatus> {
  return request<WhatsappStatus>('/whatsapp/status')
}

export function getWhatsappQr(): Promise<WhatsappQr> {
  return request<WhatsappQr>('/whatsapp/qr')
}

export function resetWhatsapp(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/whatsapp/reset', { method: 'POST' })
}
