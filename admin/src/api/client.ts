export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

export class ApiError extends Error {
  status: number
  detail?: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  const isFormData =
    typeof FormData !== 'undefined' && init.body instanceof FormData
  if (init.body !== undefined && !isFormData && !headers.has('content-type')) {
    headers.set('content-type', 'application/json')
  }
  if (API_KEY && !headers.has('x-api-key')) {
    headers.set('x-api-key', API_KEY)
  }
  const r = await fetch(`${API_URL}${path}`, { ...init, headers })
  if (r.status === 204) return undefined as T
  const text = await r.text()
  const body = text ? JSON.parse(text) : undefined
  if (!r.ok) throw new ApiError(`${r.status} ${path}`, r.status, body)
  return body as T
}
