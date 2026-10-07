import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpenText, Check, CheckCircle2, ChevronLeft, ChevronRight, CircleAlert, Clapperboard, Clock3, Link2, PenLine, RotateCcw, Save, ShieldAlert, Sparkles, Video, X } from 'lucide-react'
import { api, apiUrl } from '../api'
import { Badge, Button, EmptyState, ErrorNotice, Label } from '../components/Common'
import { JobProgress } from '../components/JobProgress'
import type { BatchDetail, CarouselSlide, ClipRange, ContentAsset, Segment } from '../types'
import { assetLabel, formatTime, splitSentences, statusLabel } from '../utils'
import { AssetStatusBadge } from './Board'

const filterLabels: Record<string, string> = { article: 'Article', newsletter: 'Newsletter', social_post: 'Social', social: 'Social', carousel: 'Carousel', clip: 'Clips', video_clip: 'Clips' }

function sentenceEvidence(asset: ContentAsset, sentence: string) {
  const normalize = (value: string) => value.replace(/\s+/g, ' ').trim()
  const excerpt = normalize(sentence)
  if (!excerpt) return undefined
  return asset.evidence_map?.find((entry) => entry.match === 'verbatim' && normalize(entry.text).includes(excerpt))
}

export function AssetDesk({ batch, asset, sourceSegments, selectedSegmentId, onSelectSegment, onAssetSelect, canEdit, workflowReady, notify }: {
  batch: BatchDetail
  asset?: ContentAsset
  sourceSegments: Segment[]
  selectedSegmentId: string | null
  onSelectSegment: (id: string) => void
  onAssetSelect: (id: string) => void
  canEdit: boolean
  workflowReady: boolean
  notify: (message: string) => void
}) {
  const [filter, setFilter] = useState('all')
  const types = [...new Set(batch.assets.map((item) => item.asset_type))]
  const visible = filter === 'all' ? batch.assets : batch.assets.filter((item) => item.asset_type === filter)
  const currentAsset = visible.find((item) => item.id === asset?.id) ?? visible[0]
  return <section className="asset-desk" aria-labelledby="asset-panel-title"><div className="panel-heading panel-heading--assets"><div><div className="panel-index">02 <span>/</span> CONTENT SUITE</div><h2 id="asset-panel-title">Edit & review</h2><p>Shape each asset, check the evidence, then approve its exact version.</p></div><span className="asset-total">{String(batch.assets.length).padStart(2, '0')}<small>ASSETS</small></span></div>
    <div className="asset-tabs" role="tablist" aria-label="Asset type">{['all', ...types].map((type) => <button role="tab" aria-selected={filter === type} className={filter === type ? 'active' : ''} key={type} onClick={() => { setFilter(type); const first = type === 'all' ? batch.assets[0] : batch.assets.find((item) => item.asset_type === type); if (first) onAssetSelect(first.id) }}>{type === 'all' ? 'All assets' : filterLabels[type] ?? assetLabel(type)} <span>{type === 'all' ? batch.assets.length : batch.assets.filter((item) => item.asset_type === type).length}</span></button>)}</div>
    {batch.assets.length === 0 ? <EmptyState icon={<Sparkles size={24} />} title="Asset generation pending">This batch has no returned assets yet. The status above will update when the workflow completes.</EmptyState> : <><div className="asset-strip" aria-label="Assets in selected category">{visible.map((item, index) => <button className={`asset-tile ${currentAsset?.id === item.id ? 'asset-tile--active' : ''}`} key={item.id} onClick={() => onAssetSelect(item.id)}><span className="asset-tile-number">{String(index + 1).padStart(2, '0')} / {assetLabel(item.asset_type)}</span><strong>{item.title || `Untitled ${assetLabel(item.asset_type).toLowerCase()}`}</strong><span className={`asset-tile-status asset-tile-status--${item.status}`}>{statusLabel(item.status)}</span></button>)}</div>{currentAsset ? <AssetEditor key={currentAsset.id} batchId={batch.batch.id} asset={currentAsset} sourceSegments={sourceSegments} selectedSegmentId={selectedSegmentId} onSelectSegment={onSelectSegment} onAssetSelect={onAssetSelect} canEdit={canEdit} workflowReady={workflowReady} notify={notify} /> : null}</>}
  </section>
}

function AssetEditor({ batchId, asset, sourceSegments, selectedSegmentId, onSelectSegment, onAssetSelect, canEdit, workflowReady, notify }: {
  batchId: string
  asset: ContentAsset
  sourceSegments: Segment[]
  selectedSegmentId: string | null
  onSelectSegment: (id: string) => void
  onAssetSelect: (id: string) => void
  canEdit: boolean
  workflowReady: boolean
  notify: (message: string) => void
}) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(asset.title)
  const [body, setBody] = useState(asset.text)
  const [sourceIds, setSourceIds] = useState(asset.source_segment_ids)
  const [slides, setSlides] = useState<CarouselSlide[]>(asset.slides ?? [])
  const [clipRange, setClipRange] = useState<ClipRange>(asset.clip_range ?? {})
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [renderJobId, setRenderJobId] = useState<string | null>(null)
  const [activeSlide, setActiveSlide] = useState(0)
  const [selectedSentence, setSelectedSentence] = useState<string | null>(null)
  const invalidate = async () => { await queryClient.invalidateQueries({ queryKey: ['batch', batchId] }); await queryClient.invalidateQueries({ queryKey: ['board-assets'] }); await queryClient.invalidateQueries({ queryKey: ['calendar'] }) }
  const edit = useMutation({ mutationFn: () => api.editAsset(asset.id, { title: title.trim(), text: body.trim(), expected_hash: asset.content_hash, source_segment_ids: sourceIds, ...(slides.length ? { slides } : {}), ...(Object.keys(clipRange).length ? { clip_range: clipRange } : {}) }), onSuccess: async (updated) => { await invalidate(); setEditing(false); onAssetSelect(updated.id); notify(`Saved as version ${updated.version}. Approval must be renewed.`) } })
  const review = useMutation({ mutationFn: (decision: 'approve' | 'reject') => api.reviewAsset(asset.id, decision, asset.content_hash, decision === 'reject' ? rejectReason.trim() : undefined), onSuccess: async (updated, decision) => { await invalidate(); setRejectOpen(false); onAssetSelect(updated.id); notify(decision === 'approve' ? 'This exact asset version was approved.' : 'Asset rejected with editorial feedback.') } })
  const regenerate = useMutation({ mutationFn: () => api.regenerateAsset(asset.id), onSuccess: async (updated) => { await invalidate(); onAssetSelect(updated.id); notify('A new asset version was requested. Manual edits on other assets remain intact.') } })
  const render = useMutation({ mutationFn: () => api.renderAsset(asset.id), onSuccess: (job) => { setRenderJobId(job.job_id ?? job.id ?? null); void queryClient.invalidateQueries({ queryKey: ['jobs', batchId] }); notify('Render requested. Progress is shown below.') } })
  const jobs = useQuery({ queryKey: ['jobs', batchId], queryFn: () => api.jobs(batchId), refetchInterval: 20_000 })
  const savedRenderJob = jobs.data?.items.find((job) => job.asset_version_id === asset.id && job.kind === 'render')
  const visibleRenderJobId = renderJobId ?? savedRenderJob?.id
  const isCarousel = asset.asset_type === 'carousel'
  const isClip = asset.asset_type === 'clip' || asset.asset_type === 'video_clip'
  const showRender = isCarousel || isClip
  const canApprove = canEdit && asset.status === 'review_pending' && asset.source_segment_ids.length > 0 && asset.warnings.length === 0
  const canRender = canEdit && workflowReady && (asset.status === 'approved' || asset.status === 'rendered') && showRender
  const sourceRefs = asset.source_segment_ids.map((id) => sourceSegments.find((segment) => segment.id === id)).filter((segment): segment is Segment => Boolean(segment))
  const allWarnings = asset.warnings ?? []
  const exactSentenceMap = selectedSentence ? sentenceEvidence(asset, selectedSentence) : undefined

  return <div className="asset-workspace"><div className="asset-workspace-heading"><div><span className="eyebrow">EDITORIAL REVIEW / VERSION {asset.version}</span><h3>{asset.title || 'Untitled asset'}</h3><div className="asset-subline"><AssetStatusBadge asset={asset} /><span>{assetLabel(asset.asset_type)}</span><span>·</span><span>{sourceRefs.length} linked source span{sourceRefs.length === 1 ? '' : 's'}</span></div></div><div className="asset-heading-actions"><Button variant="outline" onClick={() => setEditing(!editing)} disabled={!canEdit}><PenLine size={15} />{editing ? 'Close editor' : 'Edit asset'}</Button></div></div>
    {asset.status === 'stale' ? <div className="asset-alert"><ShieldAlert size={18} /><span>The source changed after this proposal. Recheck the affected claim and create a new approved version.</span></div> : null}
    {allWarnings.length ? <div className="asset-warnings"><span className="eyebrow">VALIDATION NOTES</span>{allWarnings.map((warning, index) => <div key={`${index}-${warning}`}><CircleAlert size={15} />{warning}</div>)}</div> : <div className="asset-validation"><CheckCircle2 size={16} />No validation warnings returned for this asset. Human review remains required.</div>}
    {editing ? <fieldset className="asset-edit-form"><legend>Linked source evidence</legend><p>Select the source spans supporting this working copy. Carousel slides retain their own citations; every slide citation must also be selected here.</p>{sourceSegments.map((segment) => <label className="check-row" key={segment.id}><input type="checkbox" checked={sourceIds.includes(segment.id)} onChange={(event) => setSourceIds(event.target.checked ? [...sourceIds, segment.id] : sourceIds.filter((id) => id !== segment.id))} /><span>{formatTime(segment.start_ms)}–{formatTime(segment.end_ms)} · {segment.text}</span></label>)}</fieldset> : null}
    {editing ? <form className="asset-edit-form" onSubmit={(event) => { event.preventDefault(); edit.mutate() }}><div className="edit-form-head"><span className="eyebrow">WORKING COPY</span><p>Saving creates a new version. Earlier approvals do not carry forward.</p></div><Label htmlFor="asset-title">Headline / title</Label><input id="asset-title" value={title} onChange={(event) => setTitle(event.target.value)} required /><Label htmlFor="asset-body">Body text / caption</Label><textarea id="asset-body" value={body} onChange={(event) => setBody(event.target.value)} rows={9} />{isCarousel && slides.length ? <div className="slide-edit-list"><span className="form-label">Slide copy</span>{slides.map((slide, index) => <div className="slide-edit-item" key={index}><span>{String(index + 1).padStart(2, '0')}</span><input aria-label={`Slide ${index + 1} heading`} value={slide.heading ?? ''} onChange={(event) => setSlides(slides.map((item, itemIndex) => itemIndex === index ? { ...item, heading: event.target.value } : item))} /><textarea aria-label={`Slide ${index + 1} body`} rows={2} value={slide.body ?? ''} onChange={(event) => setSlides(slides.map((item, itemIndex) => itemIndex === index ? { ...item, body: event.target.value } : item))} /></div>)}</div> : null}{isClip ? <div className="clip-edit-grid"><div><Label htmlFor="clip-start">Start (ms)</Label><input id="clip-start" type="number" min="0" value={clipRange.start_ms ?? ''} onChange={(event) => setClipRange({ ...clipRange, start_ms: Number(event.target.value) })} /></div><div><Label htmlFor="clip-end">End (ms)</Label><input id="clip-end" type="number" min="0" value={clipRange.end_ms ?? ''} onChange={(event) => setClipRange({ ...clipRange, end_ms: Number(event.target.value) })} /></div></div> : null}<div className="edit-actions"><Button type="submit" loading={edit.isPending}><Save size={16} />Save new version</Button><Button type="button" variant="text" onClick={() => setEditing(false)}><X size={16} />Cancel</Button></div>{edit.isError ? <ErrorNotice error={edit.error} title="Could not save asset" /> : null}</form> : <div className="asset-preview-grid"><div className="preview-section"><div className="preview-top"><span><BookOpenText size={16} /> CONTENT PREVIEW</span><span>v{asset.version}</span></div>{isCarousel ? <CarouselPreview asset={asset} slideIndex={activeSlide} onSlideChange={setActiveSlide} /> : isClip ? <ClipPreview asset={asset} /> : <TextPreview asset={asset} selectedSentence={selectedSentence} onSelectSentence={setSelectedSentence} onSelectSegment={onSelectSegment} />}</div><div className="review-sidebar"><div className="review-sidebar-header"><span className="eyebrow">SOURCE TRACE</span><Link2 size={17} /></div><h4>Source evidence</h4><p>These spans were returned for the asset as a whole. Verify individual claims and context before approval.</p>{sourceRefs.length ? <div className="source-ref-list">{sourceRefs.map((segment) => <button className={selectedSegmentId === segment.id ? 'active' : ''} key={segment.id} onClick={() => onSelectSegment(segment.id)}><span>{formatTime(segment.start_ms)}–{formatTime(segment.end_ms)}</span><strong>{segment.speaker || 'Source voice'}</strong><small>{segment.text}</small><ArrowUpRight size={15} /></button>)}</div> : <div className="no-evidence"><CircleAlert size={17} />No source spans available. Approval is blocked.</div>}{selectedSentence ? <div className="selected-sentence"><span>SELECTED SENTENCE</span><p>“{selectedSentence}”</p><small>{exactSentenceMap ? 'Exact verbatim excerpt matched to the highlighted source segment.' : 'Only asset-level references are available. Review source context before approving this sentence.'}</small></div> : null}</div></div>}
    <div className="review-controls"><div className="review-controls-copy"><span className="eyebrow">EDITORIAL DECISION</span><p>Approval applies to this content hash and version only.</p></div><div className="review-buttons"><Button variant="light" onClick={() => regenerate.mutate()} loading={regenerate.isPending} disabled={!canEdit}><RotateCcw size={16} />Regenerate</Button><Button variant="outline" onClick={() => setRejectOpen(!rejectOpen)} disabled={!canEdit || asset.status !== 'review_pending'}><X size={16} />Reject</Button><Button variant="orange" onClick={() => review.mutate('approve')} loading={review.isPending} disabled={!canApprove}><Check size={16} />Approve version</Button></div>{!canEdit ? <span className="action-hint">Viewer access is read only.</span> : asset.source_segment_ids.length === 0 ? <span className="action-hint">Approval requires a linked source span.</span> : allWarnings.length > 0 ? <span className="action-hint">Resolve validation warnings before approving this version.</span> : asset.status !== 'review_pending' ? <span className="action-hint">This version is {statusLabel(asset.status).toLowerCase()}. Edit or regenerate to create a new reviewable version.</span> : null}{rejectOpen ? <form className="reject-form" onSubmit={(event) => { event.preventDefault(); if (rejectReason.trim()) review.mutate('reject') }}><Label htmlFor="reject-reason">Reason for rejection</Label><textarea id="reject-reason" rows={3} value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} placeholder="What needs to change?" required /><Button type="submit" variant="dark" loading={review.isPending}>Submit rejection</Button></form> : null}{review.isError ? <ErrorNotice error={review.error} title="Review decision was not saved" /> : null}{regenerate.isError ? <ErrorNotice error={regenerate.error} title="Regeneration could not start" /> : null}</div>
    {showRender ? <div className="render-actions"><div><span className="eyebrow">PRODUCTION FILES</span><p>{!workflowReady ? 'Intake workflow unavailable. Rendering is paused until workflow setup is ready.' : isCarousel ? 'Render approved slides to PNG and PDF.' : 'Render the approved range with subtitles and title card.'}</p></div><Button variant="outline" onClick={() => render.mutate()} loading={render.isPending} disabled={!canRender}><Clapperboard size={16} />Render {isCarousel ? 'slides' : 'clip'}</Button>{render.isError ? <ErrorNotice error={render.error} title="Render could not start" /> : null}{visibleRenderJobId ? <JobProgress jobId={visibleRenderJobId} label="Asset render" onComplete={() => void invalidate()} /> : null}</div> : null}
    {(asset.status === 'approved' || asset.status === 'rendered') && ['article', 'newsletter', 'social'].includes(asset.asset_type) ? <ScheduleControls asset={asset} canEdit={canEdit} notify={notify} /> : null}
  </div>
}

function ScheduleControls({ asset, canEdit, notify }: { asset: ContentAsset; canEdit: boolean; notify: (message: string) => void }) {
  const queryClient = useQueryClient()
  const channel = asset.asset_type === 'article' ? 'wordpress' : asset.asset_type === 'newsletter' ? 'newsletter' : 'social'
  const [date, setDate] = useState('')
  const schedule = useMutation({ mutationFn: () => api.scheduleAsset(asset.id, channel, date ? new Date(date).toISOString() : null), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['calendar'] }); notify('Publication draft saved. Check the Calendar for its status.') } })
  return <form className="schedule-actions" onSubmit={(event) => { event.preventDefault(); schedule.mutate() }}><div className="schedule-actions-heading"><span className="eyebrow">PUBLICATION HANDOFF</span><p>Create a publication-ready draft. This does not publish publicly.</p></div><div className="schedule-form-row"><label><span>CHANNEL</span><input value={channel === 'wordpress' ? 'WordPress draft' : channel === 'newsletter' ? 'Newsletter draft' : 'Social draft'} readOnly aria-label="Publication channel" /></label><label><span>PLANNED DATE · OPTIONAL</span><input type="datetime-local" value={date} onChange={(event) => setDate(event.target.value)} disabled={!canEdit} /></label><Button type="submit" variant="outline" loading={schedule.isPending} disabled={!canEdit}><ArrowRight size={15} />Save draft</Button></div>{schedule.isError ? <ErrorNotice error={schedule.error} title="Publication draft was not saved" /> : null}</form>
}

function TextPreview({ asset, selectedSentence, onSelectSentence, onSelectSegment }: { asset: ContentAsset; selectedSentence: string | null; onSelectSentence: (sentence: string) => void; onSelectSegment: (id: string) => void }) {
  const sentences = splitSentences(asset.text ?? '')
  return <div className={`text-preview text-preview--${asset.asset_type}`}><div className="preview-paper-head"><span>CONTENTSTUDIO / WORKING DRAFT</span><span>#{asset.version.toString().padStart(2, '0')}</span></div><h4>{asset.title}</h4>{sentences.length ? <div className="preview-paragraph">{sentences.map((sentence, index) => { const verified = sentenceEvidence(asset, sentence); return <button key={index} className={selectedSentence === sentence ? 'selected' : ''} title={verified ? 'Jump to verbatim source context' : 'No sentence-level match; inspect source references'} onClick={() => { onSelectSentence(sentence); const id = verified?.source_segment_ids[0]; if (id) onSelectSegment(id) }}>{sentence}{' '}</button> })}</div> : <p className="preview-empty">No body text has been generated for this asset.</p>}<div className="preview-paper-foot"><span>{assetLabel(asset.asset_type).toUpperCase()}</span><span>UNPUBLISHED</span></div></div>
}

function CarouselPreview({ asset, slideIndex, onSlideChange }: { asset: ContentAsset; slideIndex: number; onSlideChange: (index: number) => void }) {
  const urls = asset.render_urls?.png ?? []
  const slides = asset.slides ?? []
  const count = urls.length || slides.length
  const safeIndex = Math.min(slideIndex, Math.max(0, count - 1))
  const slide = slides[safeIndex]
  return <div className="carousel-preview"><div className="carousel-stage">{urls[safeIndex] ? <img src={apiUrl(urls[safeIndex])} alt={`Rendered carousel slide ${safeIndex + 1} of ${count}`} /> : slide ? <div className="draft-slide"><span className="draft-slide-tag">CONTENTSTUDIO <span>/{String(safeIndex + 1).padStart(2, '0')}</span></span><div><span className="draft-slide-kicker">{slide.kicker || 'IDEAS WORTH SHARING'}</span><h4>{typeof slide.heading === 'string' && slide.heading.trim() ? slide.heading : `Slide ${safeIndex + 1}`}</h4><p>{slide.body || (slide.bullets ?? []).join(' · ')}</p></div><span className="draft-slide-foot">SOURCE-LED CONTENT <ArrowRight size={17} /></span></div> : <div className="preview-empty">No slide data returned.</div>}</div><div className="carousel-controls"><Button variant="text" onClick={() => onSlideChange(Math.max(0, safeIndex - 1))} disabled={safeIndex === 0} aria-label="Previous slide"><ChevronLeft size={18} /></Button><span>{String(safeIndex + 1).padStart(2, '0')} / {String(count).padStart(2, '0')}</span><Button variant="text" onClick={() => onSlideChange(Math.min(count - 1, safeIndex + 1))} disabled={safeIndex >= count - 1} aria-label="Next slide"><ChevronRight size={18} /></Button></div><div className="preview-file-state">{urls.length ? <><Badge tone="green">Rendered PNG</Badge>{asset.render_urls?.pdf ? <a className="file-link" href={apiUrl(asset.render_urls.pdf)} download><ArrowDownToLine size={15} />Download PDF</a> : null}</> : <><Badge tone="orange">Draft layout only</Badge><span>Actual PNG/PDF available after approval and render.</span></>}</div></div>
}

function ClipPreview({ asset }: { asset: ContentAsset }) {
  const range = asset.clip_range
  const start = range?.start_ms ?? (range?.start != null ? range.start * 1000 : null)
  const end = range?.end_ms ?? (range?.end != null ? range.end * 1000 : null)
  return <div className="clip-preview">{asset.render_urls?.mp4 ? <video controls preload="metadata" src={apiUrl(asset.render_urls.mp4)} aria-label={`Rendered clip: ${asset.title}`} /> : <div className="clip-placeholder"><div className="clip-signal"><Video size={37} strokeWidth={1.15} /></div><span>CLIP PROPOSAL</span><strong>{asset.title}</strong><p>{asset.text}</p><small>Playable video appears after approval and successful rendering.</small></div>}<div className="clip-range"><Clock3 size={16} /><span>PROPOSED RANGE</span><strong>{formatTime(start)} — {formatTime(end)}</strong><span>{range?.aspect_ratio || 'Aspect ratio pending'}</span></div>{asset.render_urls?.mp4 ? <a className="file-link" href={apiUrl(asset.render_urls.mp4)} download><ArrowDownToLine size={15} />Download MP4</a> : null}</div>
}
