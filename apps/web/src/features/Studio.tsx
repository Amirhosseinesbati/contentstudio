import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, AudioLines, BadgeCheck, CircleAlert, CircleDashed, Clock3, Download, FileText, Link2, ShieldCheck, Sparkles } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, EmptyState, ErrorNotice } from '../components/Common'
import { JobProgress } from '../components/JobProgress'
import type { BatchDetail, BatchSummary, Bootstrap, SourceAsset, SourceDetail } from '../types'
import { errorMessage, formatDate, shortId, statusLabel } from '../utils'
import { AssetDesk } from './AssetDesk'
import { BatchPicker } from './Board'
import { SourcePane } from './SourcePane'

interface QueryState<T> { data?: T; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }

export function Studio({ bootstrap, batch, source, batches, sources, selectedAssetId, onAssetSelect, onBatchSelect, onSourceSelect, onNavigate, notify, canEdit }: {
  bootstrap?: Bootstrap
  batch: QueryState<BatchDetail>
  source: QueryState<SourceDetail>
  batches: BatchSummary[]
  sources: SourceAsset[]
  selectedAssetId: string | null
  onAssetSelect: (id: string) => void
  onBatchSelect: (id: string) => void
  onSourceSelect: (id: string) => void
  onNavigate: (page: 'library' | 'board' | 'calendar' | 'studio') => void
  notify: (message: string) => void
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null)
  const [packageJobId, setPackageJobId] = useState<string | null>(null)
  const [packageReady, setPackageReady] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const data = batch.data
  const activeAsset = data?.assets.find((item) => item.id === selectedAssetId) ?? data?.assets[0]
  const approvedCount = data?.assets.filter((item) => item.status === 'approved' || item.status === 'rendered').length ?? 0
  const pendingCount = data?.assets.filter((item) => item.status === 'review_pending').length ?? 0
  const n8nReachable = bootstrap?.connection.n8n === 'connected'
  const workflowReady = bootstrap?.connection.n8n_intake === 'connected'
  const packageMutation = useMutation({ mutationFn: () => api.createPackage(data!.batch.id), onSuccess: (job) => { setPackageReady(false); setPackageJobId(job.job_id ?? job.id ?? null); notify('Package assembly started. Progress is shown below.'); void queryClient.invalidateQueries({ queryKey: ['batch', data!.batch.id] }) } })
  const download = async () => {
    if (!data) return
    setDownloadError(null)
    try {
      const response = await fetch(api.downloadUrl(data.batch.id), { credentials: 'include' })
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null
        if (response.status === 409) throw new Error(workflowReady ? 'Package is not ready. Choose Assemble package and wait for completion.' : 'No completed package is available. Activate the intake workflow before assembling one.')
        throw new Error(body?.detail || `Package unavailable (${response.status}). Assemble it first.`)
      }
      const blob = await response.blob()
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = `contentstudio-${shortId(data.batch.id).toLowerCase()}.zip`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(href), 30_000)
      notify('Package downloaded from the server.')
    } catch (error) { setDownloadError(errorMessage(error)) }
  }

  return <div className="studio-page page-enter"><div className="studio-topline"><span className="eyebrow eyebrow--orange">THE EDITORIAL DESK <span className="eyebrow-line" /> SOURCE-FIRST WORKFLOW</span><div className="studio-top-actions"><span className={`live-indicator ${n8nReachable ? 'live-indicator--on' : ''}`}><span />{n8nReachable ? 'n8n service online' : 'n8n service offline'}</span><span className={`live-indicator ${workflowReady ? 'live-indicator--on' : ''}`}><span />{workflowReady ? 'Intake ready' : 'Intake unavailable'}</span>{batches.length ? <BatchPicker items={batches} value={data?.batch.id ?? null} onChange={onBatchSelect} /> : null}</div></div>
    <div className="studio-hero"><div><h1>Ideas with <em>receipts.</em></h1><p>A working space for turning owned conversations into traceable, reviewable content.</p></div><div className="hero-rule"><span>FROM SOURCE</span><span className="rule-arrow">→</span><span>TO STORY</span></div></div>
    {!data && sources.length ? <label className="source-switch"><span>INSPECT SOURCE</span><select value={source.data?.source.id ?? sources[0]?.id ?? ''} onChange={(event) => onSourceSelect(event.target.value)}>{sources.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label> : null}
    {batch.isError ? <ErrorNotice error={batch.error} onRetry={() => void batch.refetch()} title="This content batch could not load" /> : null}
    {source.isError ? <ErrorNotice error={source.error} onRetry={() => void source.refetch()} title="The source could not load" /> : null}
    {!data && !source.data && (batch.isPending || source.isPending) ? <div className="loading-section"><CircleDashed size={22} className="spin" />Preparing editorial desk…</div> : null}
    {data ? <div className="batch-masthead"><div className="batch-masthead-left"><span className="batch-kicker">CURRENT CONTENT BATCH <span>#{shortId(data.batch.id)}</span></span><h2>{data.source.title}</h2><div className="batch-meta"><span><Clock3 size={14} />{formatDate(data.batch.created_at)}</span><span><FileText size={14} />{data.assets.length} assets</span><span><Link2 size={14} />{data.claims.length} sourced claims</span></div></div><div className="batch-status"><Badge tone={data.batch.status === 'failed' ? 'red' : data.batch.status === 'complete' ? 'green' : 'orange'}>{statusLabel(data.batch.status)}</Badge><span>{approvedCount} approved · {pendingCount} awaiting review</span></div></div> : null}
    {!data && !batch.isError && !batch.isPending ? <div className="studio-no-batch"><div className="no-batch-art"><AudioLines size={48} strokeWidth={1.1} /></div><span className="eyebrow">A SOURCE IS THE FIRST PAGE</span><h2>{source.data?.source.title ?? 'Your desk is waiting.'}</h2><p>{source.data ? 'Explore the transcript here, or create a content batch from the source library.' : 'Add an owned recording or timestamped transcript, then create a content batch.'}</p><Button variant="orange" onClick={() => onNavigate('library')}>Open source library <ArrowRight size={16} /></Button></div> : null}
    {(data || source.data) ? <div className="editorial-grid"><SourcePane source={source.data} isPending={source.isPending} claims={data?.claims ?? []} selectedSegmentId={selectedSegmentId} onSelectSegment={setSelectedSegmentId} canEdit={canEdit} onChanged={() => { void queryClient.invalidateQueries({ queryKey: ['source'] }); void queryClient.invalidateQueries({ queryKey: ['batch'] }); notify('Transcript corrected. Affected approvals must be reviewed again.') }} />{data ? <AssetDesk batch={data} asset={activeAsset} sourceSegments={source.data?.transcript?.segments ?? []} selectedSegmentId={selectedSegmentId} onSelectSegment={setSelectedSegmentId} onAssetSelect={onAssetSelect} canEdit={canEdit} workflowReady={workflowReady} notify={notify} /> : <div className="asset-side-empty"><EmptyState icon={<Sparkles size={26} />} title="No content batch selected">Create a batch for this source to generate articles, posts, a carousel, and clip proposals.<Button variant="outline" onClick={() => onNavigate('library')}>Set up batch <ArrowRight size={16} /></Button></EmptyState></div>}</div> : null}
    {data ? <section className="package-strip"><div className="package-copy"><span className="eyebrow">LAST MILE / CONTENT PACKAGE</span><h2>Everything, ready to hand off.</h2><p>Approved files, captions, source map, and a publication calendar in one download.</p></div><div className="package-actions"><Button variant="outline" onClick={() => packageMutation.mutate()} loading={packageMutation.isPending} disabled={!canEdit || approvedCount === 0 || !workflowReady}><Sparkles size={16} /> Assemble package</Button><Button onClick={() => void download()} disabled={approvedCount === 0}><Download size={16} /> Download ZIP</Button></div>{!canEdit ? <span className="package-hint">Viewer access is read only.</span> : approvedCount === 0 ? <span className="package-hint">Approve at least one asset before packaging.</span> : null}{!workflowReady ? <span className="package-hint" role="status">Intake workflow unavailable. Package assembly is paused; an existing completed ZIP can still be downloaded.</span> : null}{packageMutation.isError ? <div className="package-feedback"><ErrorNotice error={packageMutation.error} title="Package assembly failed" /></div> : null}{packageJobId ? <div className="package-feedback"><JobProgress jobId={packageJobId} label="Package assembly" onComplete={() => setPackageReady(true)} /></div> : null}{packageReady ? <span className="package-ready"><BadgeCheck size={16} />Package ready to download</span> : null}{downloadError ? <div className="package-feedback"><div className="form-error" role="alert"><CircleAlert size={16} />{downloadError}</div></div> : null}</section> : null}
    <footer className="studio-footer"><span><ShieldCheck size={17} /> Claims need human editorial judgment in context.</span><span>CONTENTSTUDIO / {bootstrap?.mode.toLowerCase() === 'demo' ? 'SYNTHETIC DEMO DATA' : 'CONNECTED WORKSPACE'}</span></footer>
  </div>
}
