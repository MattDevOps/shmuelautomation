import { request } from './client'
import type { ScheduleConfig } from './types'

export function getScheduleConfig(): Promise<ScheduleConfig> {
  return request<ScheduleConfig>('/post-queue/schedule-config')
}

export function updateScheduleConfig(
  cfg: ScheduleConfig,
): Promise<ScheduleConfig> {
  return request<ScheduleConfig>('/post-queue/schedule-config', {
    method: 'PUT',
    body: JSON.stringify(cfg),
  })
}
