import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, AudioLines, Check, CircleAlert, CircleDashed, FileAudio, FileText, LockKeyhole, UploadCloud } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, EmptyState, ErrorNotice, Label } from '../components/Common'
import type { BrandProfile, Segment, SourceAsset } from '../types'
import { errorMessage, formatDate, formatTime } from '../utils'

type FormMode = 'upload' | 'transcript'

function parseTimestamp(value: string): number | null {
  const pieces = value.trim().split(':').map(Number)
  if (!(pieces.length === 2 || pieces.length === 3) || pieces.some((n) => !Number.isFinite(n))) return null
  return pieces.reduce((total, n) => total * 60 + n, 0) * 1000
}

function parseTranscript(input: string): Pick<Segment, 'start_ms' | 'end_ms' | 'speaker' | 'text'>[] {
  const lines = input.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length === 0) throw new Error('Add at least one timestamped segment.')
  return lines.map((line, index) => {
    const match = line.match(/^([\d:]+)\s*[-–]\s*([\d:]+)\s*\|\s*([^|]+)\s*\|\s*(.+)$/)
    if (!match) throw new Error(`Line ${index + 1} needs: 00:00–00:20 | Speaker | Transcript text`)
    const start = parseTimestamp(match[1] ?? '')
    const end = parseTimestamp(match[2] ?? '')
    if (start == null || end == null || end <= start) throw new Error(`Line ${index + 1} has an invalid time range.`)
    return { start_ms: start, end_ms: end, speaker: match[3]?.trim() === '—' ? null : match[3]?.trim() ?? null, text: match[4]?.trim() ?? '' }
  })
}

export function Library({ sources, brands, onSourceSelect, onBatchSelect, notify, canEdit, workflowReady, transcriptionReady, demoMode }: {
  sources: { data?: { items: SourceAsset[] }; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }
  brands: { data?: { items: BrandProfile[] }; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }
  onSourceSelect: (id: string) => void
  onBatchSelect: (id: string) => void
  notify: (message: string) => void
  canEdit: boolean
  workflowReady: boolean
  transcriptionReady: boolean
  demoMode: boolean
}) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<FormMode>('upload')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [rights, setRights] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [parseError, setParseError] = useState<string | null>(null)
  const [brandId, setBrandId] = useState('')
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null)
  const addSource = useMutation({ mutationFn: () => {
    if (!title.trim()) throw new Error('Give this source a title.')
    if (!rights) throw new Error('Confirm that you own or are authorized to use this source.')
    if (mode === 'upload') {
      if (!file) throw new Error('Choose an audio or video file.')
      return api.uploadSource(file, title.trim(), rights)
    }
    const segments = parseTranscript(transcript)
    return api.createTranscriptSource(title.trim(), segments)
  }, onSuccess: async (data) => { await queryClient.invalidateQueries({ queryKey: ['sources'] }); setSelectedSourceId(data.source.id); setTitle(''); setTranscript(''); setFile(null); setRights(false); setParseError(null); notify(data.source.latest_transcript_version_id ? 'Timestamped transcript added. This source is ready for batch creation when intake is available.' : transcriptionReady ? 'Media uploaded. Connected transcription will run when a batch is created.' : demoMode ? 'Media stored in DEMO. Connected transcription is required before creating a batch.' : 'Media uploaded. Configure transcription before creating a batch.') }, onError: (error) => setParseError(errorMessage(error)) })
  const items = sources.data?.items ?? []
  const selectedSource = items.find((item) => item.id === selectedSourceId)
  const hasTranscript = Boolean(selectedSource?.latest_transcript_version_id)
  const sourceReady = hasTranscript || (selectedSource?.kind === 'owned_media' && transcriptionReady)
  const createBatch = useMutation({ mutationFn: () => {
    if (!selectedSourceId) throw new Error('Select a source first.')
    if (!sourceReady) throw new Error('This source needs a transcript or connected transcription before batch creation.')
    if (!(brandId || brands.data?.items[0]?.id)) throw new Error('A brand profile is required.')
    return api.createBatch(selectedSourceId, brandId || brands.data!.items[0]!.id)
  }, onSuccess: async (result) => { await queryClient.invalidateQueries({ queryKey: ['batches'] }); notify('Content batch queued. Its state will update as the workflow runs.'); onBatchSelect(result.batch.id) } })
  return <div className="library-page page-enter"><div className="page-heading"><div><span className="eyebrow eyebrow--orange">INBOX / OWNED SOURCES</span><h1>The source library.</h1><p>Start with a recording or an explicitly timestamped transcript. Every derived asset keeps a path back here.</p></div><div className="library-heading-art"><AudioLines size={40} strokeWidth={1.15} /></div></div>
    <div className="library-grid"><section className="intake-card"><div className="intake-card-head"><span className="eyebrow">01 / NEW SOURCE</span><h2>Bring in a conversation.</h2><p>Keep rights and provenance clear from the start.</p></div><div className="segmented-control" role="tablist" aria-label="Source intake mode"><button role="tab" aria-selected={mode === 'upload'} className={mode === 'upload' ? 'active' : ''} onClick={() => { setMode('upload'); setParseError(null) }}><UploadCloud size={17} />Media upload</button><button role="tab" aria-selected={mode === 'transcript'} className={mode === 'transcript' ? 'active' : ''} onClick={() => { setMode('transcript'); setParseError(null) }}><FileText size={17} />Transcript only</button></div><form onSubmit={(event) => { event.preventDefault(); setParseError(null); addSource.mutate() }}><Label htmlFor="source-title">Source title</Label><input id="source-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. A practical guide to customer interviews" required disabled={!canEdit} />
      {mode === 'upload' ? <><Label htmlFor="media-file">Audio or video file</Label><label className="upload-drop" htmlFor="media-file"><UploadCloud size={26} /><strong>{file?.name ?? 'Choose a media file'}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB selected` : 'MP3, WAV, M4A, MP4 or WebM · validated by server'}</span></label><input id="media-file" className="sr-only" type="file" accept="audio/*,video/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} disabled={!canEdit} /><p className="field-hint">{demoMode ? 'DEMO uploads are stored without a transcript. Configure connected transcription to create a batch from new media, or add a timestamped transcript.' : transcriptionReady ? 'Connected transcription runs when you create a batch from this media.' : 'Configure connected transcription before creating a batch from this media.'}</p></> : <><Label htmlFor="transcript-input">Timestamped transcript</Label><textarea id="transcript-input" rows={7} value={transcript} onChange={(event) => setTranscript(event.target.value)} disabled={!canEdit} placeholder={'00:00–00:20 | Host | Welcome to today\'s discussion.\n00:20–00:45 | Guest | Let me give you some context.'} /><p className="field-hint">One segment per line: start–end | speaker | exact words. These are your supplied timestamps; no audio alignment is claimed.</p></>}
      <label className="check-row"><input type="checkbox" checked={rights} onChange={(event) => setRights(event.target.checked)} disabled={!canEdit} /><span><strong>I own or am authorized to use this source</strong><small>Upload and processing require source rights.</small></span></label>{parseError || addSource.isError ? <div className="form-error" role="alert"><CircleAlert size={16} />{parseError || errorMessage(addSource.error)}</div> : null}<Button type="submit" variant="orange" loading={addSource.isPending} disabled={!canEdit}>{mode === 'upload' ? 'Upload source' : 'Add transcript'} <ArrowRight size={16} /></Button>{!canEdit ? <p className="field-hint">Viewer access is read only.</p> : null}</form></section>
      <section className="source-catalog"><div className="catalog-heading"><div><span className="eyebrow">SOURCE ARCHIVE</span><h2>{items.length} conversation{items.length === 1 ? '' : 's'}</h2></div><span className="catalog-indicator"><span />WORKSPACE SCOPED</span></div>{sources.isError ? <ErrorNotice error={sources.error} onRetry={() => void sources.refetch()} /> : sources.isPending ? <div className="loading-section"><CircleDashed size={20} className="spin" />Loading sources…</div> : items.length === 0 ? <EmptyState icon={<FileAudio size={25} />} title="Your library is ready">Upload owned media for later transcription, or add a timestamped transcript to begin.</EmptyState> : <div className="source-list">{items.map((source, index) => <button key={source.id} className={`source-list-item ${selectedSourceId === source.id ? 'selected' : ''}`} onClick={() => setSelectedSourceId(source.id)}><span className="source-number">{String(index + 1).padStart(2, '0')}</span><span className="source-list-main"><strong>{source.title}</strong><small>{formatDate(source.created_at)} · {source.duration_ms ? formatTime(source.duration_ms) : 'Transcript fixture'} · {source.batch_count ?? 0} batches</small></span><Badge tone={!source.latest_transcript_version_id ? 'orange' : source.kind?.includes('transcript') ? 'blue' : 'neutral'}>{!source.latest_transcript_version_id ? 'Needs transcript' : source.kind?.includes('transcript') ? 'Transcript only' : 'Media ready'}</Badge><ArrowRight size={17} /></button>)}</div>}
        {selectedSourceId ? <div className="source-actions"><Button variant="outline" onClick={() => onSourceSelect(selectedSourceId)}>{hasTranscript ? 'Inspect transcript' : 'Inspect source'} <ArrowRight size={16} /></Button><div className="batch-create"><label className="form-label" htmlFor="brand-profile">Brand profile</label>{brands.isError ? <ErrorNotice error={brands.error} onRetry={() => void brands.refetch()} title="Brand profiles unavailable" /> : <select id="brand-profile" value={brandId || brands.data?.items[0]?.id || ''} onChange={(event) => setBrandId(event.target.value)} disabled={brands.isPending || !canEdit}>{brands.data?.items.map((brand) => <option value={brand.id} key={brand.id}>{brand.name} · v{brand.version}</option>)}</select>}<Button onClick={() => createBatch.mutate()} loading={createBatch.isPending} disabled={!canEdit || !brands.data?.items.length || !workflowReady || !sourceReady}>Create content batch <ArrowRight size={16} /></Button>{createBatch.isError ? <div className="form-error" role="alert"><CircleAlert size={16} />{errorMessage(createBatch.error)}</div> : null}<small role="status">{!selectedSource ? 'Loading source readiness…' : !sourceReady ? demoMode && selectedSource.kind === 'owned_media' ? 'This DEMO media upload has no transcript. Connected transcription is required before batch creation.' : 'This source needs a transcript or connected transcription before batch creation.' : !workflowReady ? 'Intake workflow unavailable. Activate the n8n workflow pack to create a batch.' : hasTranscript ? 'Transcript ready. The n8n intake workflow can generate a new batch.' : 'Connected transcription will run when this batch starts. Review its transcript before approving content.'}</small></div></div> : null}
      </section></div><div className="library-bottom-note"><LockKeyhole size={18} /><span>Sources stay scoped to this workspace. Uploads and corrections are versioned; source changes can invalidate affected approvals.</span><Check size={17} /></div>
  </div>
}
