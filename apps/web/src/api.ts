import type { ApiRequest, ApiResponse } from './openapi.generated'
import type { ContentAsset, Segment } from './types'

const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  constructor(message: string, public status: number, public details?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

export function apiUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(apiUrl(`/api/v1${path}`), {
      credentials: 'include',
      headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    })
  } catch {
    throw new ApiError('The ContentStudio service is unreachable. Check that the API is running, then retry.', 0)
  }
  if (!response.ok) {
    const raw = await response.text().catch(() => '')
    let details: unknown = raw
    if (raw) {
      try { details = JSON.parse(raw) as unknown } catch { /* A proxy or upstream may return plain text or HTML. */ }
    }
    const plainText = typeof details === 'string' && !/<(?:!doctype|html|body)\b/i.test(details)
      ? details.replace(/\s+/g, ' ').trim().slice(0, 240)
      : ''
    const message = typeof details === 'object' && details !== null && 'detail' in details
      ? typeof details.detail === 'string' ? details.detail : JSON.stringify(details.detail)
      : plainText || (response.status >= 500
        ? `ContentStudio service error (HTTP ${response.status}). Check that the API is running, then retry.`
        : `Request failed (HTTP ${response.status}).`)
    throw new ApiError(message, response.status, details)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (value: unknown) => JSON.stringify(value)

export const api = {
  me: () => request<ApiResponse<'/api/v1/auth/me', 'get'>>('/auth/me'),
  login: (email: string, password: string) => request<ApiResponse<'/api/v1/auth/login', 'post'>>('/auth/login', { method: 'POST', body: json({ email, password } satisfies ApiRequest<'/api/v1/auth/login', 'post'>) }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  bootstrap: () => request<ApiResponse<'/api/v1/bootstrap', 'get'>>('/bootstrap'),
  sources: () => request<ApiResponse<'/api/v1/sources', 'get'>>('/sources'),
  source: (id: string) => request<ApiResponse<'/api/v1/sources/{source_id}', 'get'>>(`/sources/${encodeURIComponent(id)}`),
  brands: () => request<ApiResponse<'/api/v1/brands', 'get'>>('/brands'),
  createBrand: (payload: ApiRequest<'/api/v1/brands', 'post'>) => request<ApiResponse<'/api/v1/brands', 'post'>>('/brands', { method: 'POST', body: json(payload) }),
  reviseBrand: (id: string, payload: ApiRequest<'/api/v1/brands/{brand_id}', 'put'>) => request<ApiResponse<'/api/v1/brands/{brand_id}', 'put'>>(`/brands/${encodeURIComponent(id)}`, { method: 'PUT', body: json(payload) }),
  batches: () => request<ApiResponse<'/api/v1/batches', 'get'>>('/batches'),
  batch: (id: string) => request<ApiResponse<'/api/v1/batches/{batch_id}', 'get'>>(`/batches/${encodeURIComponent(id)}`),
  calendar: () => request<ApiResponse<'/api/v1/calendar', 'get'>>('/calendar'),
  uploadSource: (file: File, title: string, rightsAttested: boolean) => {
    const form = new FormData()
    form.set('file', file)
    form.set('title', title)
    form.set('rights_attested', String(rightsAttested))
    return request<ApiResponse<'/api/v1/sources/upload', 'post'>>('/sources/upload', { method: 'POST', body: form })
  },
  createTranscriptSource: (title: string, segments: Pick<Segment, 'start_ms' | 'end_ms' | 'speaker' | 'text'>[]) =>
    request<ApiResponse<'/api/v1/sources/transcript', 'post'>>('/sources/transcript', { method: 'POST', body: json({ title, rights_attested: true, segments } satisfies ApiRequest<'/api/v1/sources/transcript', 'post'>) }),
  correctSegment: (sourceId: string, segmentId: string, text: string, expectedTranscriptId?: string) =>
    request<ApiResponse<'/api/v1/sources/{source_id}/segments/{segment_id}', 'patch'>>(`/sources/${encodeURIComponent(sourceId)}/segments/${encodeURIComponent(segmentId)}`, { method: 'PATCH', body: json({ text, expected_transcript_id: expectedTranscriptId } satisfies ApiRequest<'/api/v1/sources/{source_id}/segments/{segment_id}', 'patch'>) }),
  createBatch: (sourceId: string, brandProfileId: string) =>
    request<ApiResponse<'/api/v1/sources/{source_id}/batches', 'post'>>(`/sources/${encodeURIComponent(sourceId)}/batches`, { method: 'POST', body: json({ brand_profile_id: brandProfileId } satisfies ApiRequest<'/api/v1/sources/{source_id}/batches', 'post'>) }),
  editAsset: (id: string, changes: Partial<Pick<ContentAsset, 'title' | 'text' | 'slides' | 'clip_range' | 'source_segment_ids'>> & { expected_hash?: string }) =>
    request<ApiResponse<'/api/v1/assets/{asset_id}', 'patch'>>(`/assets/${encodeURIComponent(id)}`, { method: 'PATCH', body: json(changes satisfies ApiRequest<'/api/v1/assets/{asset_id}', 'patch'>) }),
  reviewAsset: (id: string, decision: 'approve' | 'reject', expectedHash: string, reason?: string) =>
    request<ApiResponse<'/api/v1/assets/{asset_id}/review', 'post'>>(`/assets/${encodeURIComponent(id)}/review`, { method: 'POST', body: json({ decision, expected_hash: expectedHash, reason } satisfies ApiRequest<'/api/v1/assets/{asset_id}/review', 'post'>) }),
  regenerateAsset: (id: string) => request<ApiResponse<'/api/v1/assets/{asset_id}/regenerate', 'post'>>(`/assets/${encodeURIComponent(id)}/regenerate`, { method: 'POST' }),
  renderAsset: (id: string) => request<ApiResponse<'/api/v1/assets/{asset_id}/render', 'post'>>(`/assets/${encodeURIComponent(id)}/render`, { method: 'POST' }),
  createPackage: (id: string) => request<ApiResponse<'/api/v1/batches/{batch_id}/package', 'post'>>(`/batches/${encodeURIComponent(id)}/package`, { method: 'POST' }),
  scheduleAsset: (id: string, channel: 'wordpress' | 'newsletter' | 'social', scheduledAt: string | null) =>
    request<ApiResponse<'/api/v1/assets/{asset_id}/schedule', 'post'>>(`/assets/${encodeURIComponent(id)}/schedule`, { method: 'POST', body: json({ channel, scheduled_at: scheduledAt } satisfies ApiRequest<'/api/v1/assets/{asset_id}/schedule', 'post'>) }),
  job: (id: string) => request<ApiResponse<'/api/v1/jobs/{job_id}', 'get'>>(`/jobs/${encodeURIComponent(id)}`),
  jobs: (batchId: string) => request<ApiResponse<'/api/v1/jobs', 'get'>>(`/jobs?batch_id=${encodeURIComponent(batchId)}`),
  jobEventsUrl: (id: string) => apiUrl(`/api/v1/jobs/${encodeURIComponent(id)}/events`),
  downloadUrl: (id: string) => apiUrl(`/api/v1/batches/${encodeURIComponent(id)}/download`),
}
