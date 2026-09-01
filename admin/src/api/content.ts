import { request } from './client'
import type { BlogPost, NeighborhoodContent, SitePage } from './types'

// ---- blog ----
export function listBlogPosts(): Promise<BlogPost[]> {
  return request<BlogPost[]>('/content/blog')
}

export function createBlogPost(payload: Partial<BlogPost>): Promise<BlogPost> {
  return request<BlogPost>('/content/blog', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateBlogPost(
  id: string,
  payload: Partial<BlogPost>,
): Promise<BlogPost> {
  return request<BlogPost>(`/content/blog/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteBlogPost(id: string): Promise<void> {
  return request<void>(`/content/blog/${id}`, { method: 'DELETE' })
}

// ---- neighborhoods ----
export function listNeighborhoodContent(): Promise<NeighborhoodContent[]> {
  return request<NeighborhoodContent[]>('/content/neighborhoods')
}

export function createNeighborhood(
  payload: Partial<NeighborhoodContent>,
): Promise<NeighborhoodContent> {
  return request<NeighborhoodContent>('/content/neighborhoods', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateNeighborhood(
  id: string,
  payload: Partial<NeighborhoodContent>,
): Promise<NeighborhoodContent> {
  return request<NeighborhoodContent>(`/content/neighborhoods/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteNeighborhood(id: string): Promise<void> {
  return request<void>(`/content/neighborhoods/${id}`, { method: 'DELETE' })
}

// ---- pages ----
export function listSitePages(): Promise<SitePage[]> {
  return request<SitePage[]>('/content/pages')
}

export function updateSitePage(
  id: string,
  payload: Partial<SitePage>,
): Promise<SitePage> {
  return request<SitePage>(`/content/pages/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
