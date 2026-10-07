export type Role = 'admin' | 'operator' | 'viewer'
export type AssetStatus = 'review_pending' | 'approved' | 'rejected' | 'rendered' | 'stale' | string

export interface User {
  id: string
  email: string
  role: Role
  workspace_id: string
}

export interface AuthSession {
  user: User
  mode: 'DEMO' | 'CONNECTED' | string
}

export interface Bootstrap extends AuthSession {
  workspace: { id: string; name: string }
  connection: Record<string, boolean | string | null>
  stats?: Record<string, number>
}

export interface SourceAsset {
  id: string
  title: string
  kind: string
  mime_type?: string | null
  duration_ms: number | null
  rights_status: string
  created_at: string
  latest_transcript_version_id?: string | null
  batch_count?: number
}

export interface Segment {
  id: string
  start_ms: number
  end_ms: number
  speaker: string | null
  text: string
}

export interface TranscriptVersion {
  id: string
  version: number
  segments: Segment[]
}

export interface SourceDetail {
  source: SourceAsset
  transcript: TranscriptVersion | null
  media_url: string | null
  media_status?: 'available' | 'missing' | 'transcript_only'
}

export interface BrandProfile {
  id: string
  name: string
  version: number
  tone?: string
  rules?: string[] | Record<string, unknown>
}

export interface BatchSummary {
  id: string
  source_id?: string
  source_asset_id?: string
  brand_profile_id?: string
  brand_profile_version_id?: string
  status: string
  created_at: string
  updated_at?: string
  asset_count?: number
  title?: string
}

export interface Claim {
  id: string
  text: string
  source_segment_ids: string[]
  verification_status: string
  warning?: string | null
}

export interface CarouselSlide {
  heading?: string
  body?: string
  kicker?: string
  bullets?: string[]
  [key: string]: unknown
}

export interface ClipRange {
  start_ms?: number
  end_ms?: number
  start?: number
  end?: number
  aspect_ratio?: string
  [key: string]: unknown
}

export interface RenderUrls {
  png?: string[]
  pdf?: string | null
  mp4?: string | null
}

export interface ContentAsset {
  id: string
  asset_type: string
  title: string
  text: string
  status: AssetStatus
  version: number
  content_hash: string
  source_segment_ids: string[]
  evidence_map?: { text: string; source_segment_ids: string[]; match: 'verbatim' | string }[]
  warnings: string[]
  slides?: CarouselSlide[] | null
  clip_range?: ClipRange | null
  render_urls?: RenderUrls | null
  created_at?: string
}

export interface BatchDetail {
  batch: BatchSummary
  source: SourceAsset
  claims: Claim[]
  assets: ContentAsset[]
}

export interface Job {
  id?: string
  job_id?: string
  status: string
  progress?: number
  failure_reason?: string | null
  error?: string | null
  result?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
}

export interface CalendarItem {
  id: string
  title?: string
  channel?: string
  status?: string
  scheduled_at?: string | null
  publish_at?: string | null
  asset_id?: string
  asset_version_id?: string
  batch_id?: string
  [key: string]: unknown
}

export interface ApiList<T> {
  items: T[]
}
