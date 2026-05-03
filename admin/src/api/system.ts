import { request } from './client'
import type { SystemStatus } from './types'

export function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>('/system')
}
