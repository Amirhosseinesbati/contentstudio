import type { AssetStatus } from './types'

export function formatTime(ms: number | null | undefined) {
  if (ms == null || !Number.isFinite(ms)) return '—'
  const seconds = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

export function formatDate(value: string | null | undefined) {
  if (!value) return 'Unscheduled'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

export function statusLabel(value: AssetStatus) {
  const labels: Record<string, string> = {
    review_pending: 'Needs review', approved: 'Approved', rejected: 'Rejected', rendered: 'Rendered', stale: 'Source changed',
    queued: 'Queued', transcribing: 'Transcribing', generating: 'Generating', review: 'In review', failed: 'Failed', complete: 'Complete',
  }
  return labels[value] ?? value.replace(/_/g, ' ')
}

export function assetLabel(value: string) {
  const labels: Record<string, string> = { article: 'Article', newsletter: 'Newsletter', social_post: 'Social post', social: 'Social post', carousel: 'Carousel', clip: 'Video excerpt', video_clip: 'Video excerpt' }
  return labels[value] ?? value.replace(/_/g, ' ')
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please retry.'
}

export function shortId(id: string) { return id.slice(0, 8).toUpperCase() }

export function splitSentences(text: string) {
  return text.match(/[^.!?\n]+(?:[.!?]+|\n|$)/g)?.map((item) => item.trim()).filter(Boolean) ?? []
}
