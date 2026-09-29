import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ArrowUpRight, AudioLines, BadgeCheck, CircleAlert, FileText, Link2, PenLine, Play, Quote, Save, X } from 'lucide-react'
import { api, apiUrl } from '../api'
import { Badge, Button, EmptyState } from '../components/Common'
import type { Claim, Segment, SourceDetail } from '../types'
import { errorMessage, formatTime } from '../utils'

export function SourcePane({ source, isPending, claims, selectedSegmentId, onSelectSegment, canEdit, onChanged }: {
  source?: SourceDetail
  isPending: boolean
  claims: Claim[]
  selectedSegmentId: string | null
  onSelectSegment: (id: string) => void
  canEdit: boolean
  onChanged: () => void
}) {
  const [tab, setTab] = useState<'transcript' | 'claims'>('transcript')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draftText, setDraftText] = useState('')
  const audioRef = useRef<HTMLAudioElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const save = useMutation({ mutationFn: ({ segmentId, text }: { segmentId: string; text: string }) => api.correctSegment(source!.source.id, segmentId, text), onSuccess: () => { setEditingId(null); onChanged() } })
  useEffect(() => { if (selectedSegmentId && tab === 'transcript') document.getElementById(`segment-${selectedSegmentId}`)?.scrollIntoView({ block: 'nearest' }) }, [selectedSegmentId, tab])
  const select = (segment: Segment) => {
    onSelectSegment(segment.id)
    const seconds = segment.start_ms / 1000
    if (audioRef.current) audioRef.current.currentTime = seconds
    if (videoRef.current) videoRef.current.currentTime = seconds
  }
  const selectClaim = (claim: Claim) => { const id = claim.source_segment_ids[0]; if (id) { onSelectSegment(id); setTab('transcript') } }
  const segments = source?.transcript?.segments ?? []
  const hasVideo = source?.source.mime_type?.startsWith('video/') || source?.source.kind?.includes('video') || /\.(mp4|webm|mov)(\?|$)/i.test(source?.media_url ?? '')
  return <section className="source-pane" aria-labelledby="source-panel-title"><div className="panel-heading"><div className="panel-index">01 <span>/</span> SOURCE MATERIAL</div><h2 id="source-panel-title">The original voice.</h2><p>Read the source before shaping the story.</p></div>
    {source?.media_url ? <div className="source-player"><div className="player-head"><span><Play size={13} fill="currentColor" /> OWNED SOURCE PLAYBACK</span><span>{formatTime(source.source.duration_ms)}</span></div>{hasVideo ? <video ref={videoRef} src={apiUrl(source.media_url)} controls preload="metadata" aria-label={`Play ${source.source.title}`} /> : <audio ref={audioRef} src={apiUrl(source.media_url)} controls preload="metadata" aria-label={`Play ${source.source.title}`} />}<div className="player-caption"><AudioLines size={16} />Click a transcript timestamp to seek to that point.</div></div> : <div className="fixture-banner"><FileText size={17} /><span>Transcript-only source. Timing was supplied with the text; no playable audio or measured alignment is available.</span></div>}
    <div className="source-tabs" role="tablist" aria-label="Source information"><button role="tab" aria-selected={tab === 'transcript'} className={tab === 'transcript' ? 'active' : ''} onClick={() => setTab('transcript')}>Transcript <span>{segments.length}</span></button><button role="tab" aria-selected={tab === 'claims'} className={tab === 'claims' ? 'active' : ''} onClick={() => setTab('claims')}>Claim ledger <span>{claims.length}</span></button></div>
    {isPending ? <div className="source-loading">Loading source…</div> : !source ? <EmptyState title="No source selected">Choose a source from the library.</EmptyState> : tab === 'transcript' ? <div className="transcript-wrap"><div className="transcript-meta"><span>TRANSCRIPT · VERSION {source.transcript?.version ?? '—'}</span><span>{segments.length} SEGMENTS</span></div>{segments.length === 0 ? <EmptyState title="Transcript pending">The transcription workflow has not delivered any segments yet.</EmptyState> : <div className="transcript-list">{segments.map((segment) => <div id={`segment-${segment.id}`} className={`transcript-segment ${selectedSegmentId === segment.id ? 'transcript-segment--selected' : ''}`} key={segment.id}><button className="segment-time" onClick={() => select(segment)} title={`Seek to ${formatTime(segment.start_ms)}`}><span>{formatTime(segment.start_ms)}</span><Play size={11} fill="currentColor" /></button><div className="segment-content"><div className="segment-top"><span className="speaker-name">{segment.speaker || 'Speaker unspecified'}</span>{canEdit && editingId !== segment.id ? <button className="segment-edit" onClick={() => { setEditingId(segment.id); setDraftText(segment.text) }} title="Correct this transcript segment" aria-label={`Correct segment at ${formatTime(segment.start_ms)}`}><PenLine size={14} /></button> : null}</div>{editingId === segment.id ? <form onSubmit={(event) => { event.preventDefault(); if (draftText.trim() && draftText.trim() !== segment.text) save.mutate({ segmentId: segment.id, text: draftText.trim() }); else setEditingId(null) }}><textarea value={draftText} onChange={(event) => setDraftText(event.target.value)} aria-label="Corrected transcript text" rows={4} required /><div className="segment-edit-actions"><Button type="submit" variant="dark" loading={save.isPending}><Save size={14} />Save correction</Button><Button type="button" variant="text" onClick={() => setEditingId(null)}><X size={14} />Cancel</Button></div>{save.isError ? <div className="form-error" role="alert"><CircleAlert size={14} />{errorMessage(save.error)}</div> : null}</form> : <button className="segment-text" onClick={() => select(segment)}>{segment.text}</button>}</div></div>)}</div>}</div> : <div className="claims-wrap"><div className="claims-intro"><Quote size={20} /><p>Claims below are linked to transcript segments. Selecting one jumps to its source. Verification status is a workflow result, not a replacement for editorial judgment.</p></div>{claims.length === 0 ? <EmptyState icon={<Link2 size={24} />} title="No claim ledger yet">Claims will appear after a content batch is analyzed.</EmptyState> : <div className="claim-list">{claims.map((claim, index) => <button className="claim-item" key={claim.id} onClick={() => selectClaim(claim)} disabled={claim.source_segment_ids.length === 0}><div className="claim-number">{String(index + 1).padStart(2, '0')}</div><div><div className="claim-top"><Badge tone={claim.verification_status === 'verified' ? 'green' : 'orange'}>{claim.verification_status === 'verified' ? <BadgeCheck size={13} /> : <CircleAlert size={13} />}{claim.verification_status.replace(/_/g, ' ')}</Badge><span>{claim.source_segment_ids.length} source span{claim.source_segment_ids.length === 1 ? '' : 's'}</span></div><p>{claim.text}</p>{claim.warning ? <small className="claim-warning">{claim.warning}</small> : null}</div><ArrowUpRight size={17} /></button>)}</div>}</div>}
    <div className="source-pane-foot"><span><Link2 size={15} /> SOURCE PROVENANCE</span><span>{source?.source.rights_status || 'Rights status unavailable'}</span></div>
  </section>
}
