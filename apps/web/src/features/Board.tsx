import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, CircleDashed, FileStack, RefreshCw } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, EmptyState, ErrorNotice } from '../components/Common'
import type { BatchSummary, ContentAsset } from '../types'
import { assetLabel, formatDate, shortId, statusLabel } from '../utils'

const columns = [
  { title: 'Needs review', statuses: ['review_pending'], tone: 'orange' as const, number: '01' },
  { title: 'Approved', statuses: ['approved'], tone: 'green' as const, number: '02' },
  { title: 'Rendered', statuses: ['rendered'], tone: 'blue' as const, number: '03' },
  { title: 'Attention', statuses: ['rejected', 'stale'], tone: 'red' as const, number: '04' },
]

export function Board({ batches, onOpen }: { batches: { data?: { items: BatchSummary[] }; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }; onOpen: (id: string, assetId?: string) => void }) {
  const details = useQuery({ queryKey: ['board-assets', batches.data?.items.map((item) => item.id).join(',')], queryFn: async () => {
    const all = await Promise.all((batches.data?.items ?? []).map(async (batch) => ({ batch, detail: await api.batch(batch.id) })))
    return all.flatMap(({ batch, detail }) => detail.assets.map((asset) => ({ batch, asset, sourceTitle: detail.source.title })))
  }, enabled: !!batches.data?.items.length })
  if (batches.isError) return <ErrorNotice error={batches.error} onRetry={() => void batches.refetch()} title="Content board unavailable" />
  if (batches.isPending || details.isPending) return <div className="loading-section"><CircleDashed size={22} className="spin" />Loading the content board…</div>
  if (details.isError) return <ErrorNotice error={details.error} onRetry={() => void details.refetch()} title="Asset status unavailable" />
  const rows = details.data ?? []
  return <div className="board-page page-enter"><div className="page-heading"><div><span className="eyebrow eyebrow--orange">CONTENT OPERATIONS / BOARD</span><h1>Every story, in motion.</h1><p>Review assets by state. Open any card to inspect the text, source references, and render.</p></div><div className="page-heading-aside"><span className="big-stat">{rows.length.toString().padStart(2, '0')}</span><span>ASSET VERSIONS<br />ACROSS {batches.data?.items.length ?? 0} BATCHES</span></div></div>
    {rows.length === 0 ? <EmptyState icon={<FileStack size={25} />} title="No content assets yet">Create a batch from a source in the library to begin an editorial run.</EmptyState> : <div className="board-columns">{columns.map((column) => { const cards = rows.filter(({ asset }) => column.statuses.includes(asset.status)); return <section className="board-column" key={column.title}><div className="board-column-head"><div><span className="column-number">{column.number}</span><h2>{column.title}</h2></div><span className="column-count">{cards.length.toString().padStart(2, '0')}</span></div><div className="board-stack">{cards.length ? cards.map(({ asset, batch, sourceTitle }) => <button className="board-card" key={asset.id} onClick={() => onOpen(batch.id, asset.id)}><div className="board-card-top"><Badge tone={column.tone}>{assetLabel(asset.asset_type)}</Badge><ArrowRight size={17} /></div><h3>{asset.title || 'Untitled asset'}</h3><p>{asset.text?.slice(0, 118) || (typeof asset.slides?.[0]?.body === 'string' ? asset.slides[0].body : 'Structured asset preview')}</p><div className="board-card-bottom"><span>{sourceTitle}</span><span>v{asset.version}</span></div>{asset.warnings?.length ? <span className="card-warning">{asset.warnings.length} evidence or brand warning{asset.warnings.length > 1 ? 's' : ''}</span> : null}</button>) : <div className="board-empty">No assets in this stage</div>}</div></section> })}</div>}
    <div className="board-footer"><CheckCircle2 size={17} /><span>Asset approval is tied to its exact version. Source corrections may return dependent work to review.</span><Button variant="text" onClick={() => void details.refetch()}><RefreshCw size={15} /> Refresh board</Button></div>
  </div>
}

export function BatchPicker({ items, value, onChange }: { items: BatchSummary[]; value: string | null; onChange: (id: string) => void }) {
  if (!items.length) return null
  return <label className="batch-select-wrap"><span className="sr-only">Select content batch</span><select value={value ?? items[0]?.id} onChange={(event) => onChange(event.target.value)}>{items.map((item) => <option value={item.id} key={item.id}>{item.title || `Batch ${shortId(item.id)}`} · {statusLabel(item.status)} · {formatDate(item.created_at)}</option>)}</select></label>
}

export function AssetStatusBadge({ asset }: { asset: ContentAsset }) {
  const tone = asset.status === 'approved' ? 'green' : asset.status === 'rendered' ? 'blue' : asset.status === 'review_pending' ? 'orange' : asset.status === 'rejected' || asset.status === 'stale' ? 'red' : 'neutral'
  return <Badge tone={tone}>{statusLabel(asset.status)}</Badge>
}
