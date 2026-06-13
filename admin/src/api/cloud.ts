import { API_URL, request } from './client'
import type {
  CloudConnectionStatus,
  CloudPhoto,
  PhotoUrlImportResult,
} from './types'

export const CONNECT_GOOGLE_URL = `${API_URL}/auth/google/start`

export function getCloudStatus(): Promise<CloudConnectionStatus> {
  return request<CloudConnectionStatus>('/auth/google/status')
}

export function disconnectCloud(): Promise<void> {
  return request<void>('/auth/google/disconnect', { method: 'POST' })
}

export function listPhotos(propertyId: string): Promise<CloudPhoto[]> {
  return request<CloudPhoto[]>(`/properties/${propertyId}/photos`)
}

export async function uploadPhoto(
  propertyId: string,
  file: File,
): Promise<CloudPhoto> {
  const form = new FormData()
  form.append('file', file)
  // Don't set content-type; browser sets it with the multipart boundary.
  return request<CloudPhoto>(`/properties/${propertyId}/photos`, {
    method: 'POST',
    body: form,
  })
}

export function importPhotosFromUrls(
  propertyId: string,
  imageUrls: string[],
): Promise<PhotoUrlImportResult> {
  return request<PhotoUrlImportResult>(
    `/properties/${propertyId}/photos/import-urls`,
    {
      method: 'POST',
      body: JSON.stringify({ image_urls: imageUrls }),
    },
  )
}

export function deletePhoto(propertyId: string, photoId: string): Promise<void> {
  return request<void>(`/properties/${propertyId}/photos/${photoId}`, {
    method: 'DELETE',
  })
}
