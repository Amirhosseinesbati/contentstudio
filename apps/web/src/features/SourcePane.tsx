import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ArrowUpRight, AudioLines, BadgeCheck, CircleAlert, FileText, Link2, PenLine, Play, Quote, Save, X } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, EmptyState } from '../components/Common'
import { MediaPlayback } from '../components/MediaPlayback'
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
  const save = useMutation({ mutationFn: ({ segmentId, text }: { segmentId: string; text: string }) => api.correctSegment(source!.source.id, segmentId, text, source?.transcript?.id), onSuccess: () => { setEditingId(null); onChanged() } })
  useEffect(() => { if (selectedSegmentId && tab === 'transcript') document.getElementById(`segment-${selectedSegmentId}`)?.scrollIntoView({ block: 'nearest' }) }, [selectedSegmentId, tab])
  const select = (segment: Segment) => {
    onSelectSegment(segment.id)
    const seconds = segment.start_ms / 1000
    if (audioRef.current) audioRef.current.currentTime = seconds
    if (videoRef.current) videoRef.current.currentTime = seconds
  }
  const selectClaim = (claim: Claim) => { const id = claim.source_segment_ids[0]; if (id) { onSelectSegment(id); setTab('transcript') } }
  const segments = source?.transcript?.segments ?? []
  const timelineDuration = Math.max(1, source?.source.duration_ms ?? 0, ...segments.map((segment) => segment.end_ms))
  const hasVideo = source?.source.mime_type?.startsWith('video/') || source?.source.kind?.includes('video') || /\.(mp4|webm|mov)(\?|$)/i.test(source?.media_url ?? '')
  return <section className="source-pane" aria-labelledby="source-panel-title"><div className="panel-heading"><div className="panel-index">01 <span>/</span> SOURCE MATERIAL</div><h2 id="source-panel-title">Source & transcript</h2><p>Original context. Timestamped evidence. Versioned corrections.</p></div>
    {source?.media_url ? <div className="source-player"><div className="player-head"><span><Play size={13} fill="currentColor" /> OWNED SOURCE PLAYBACK</span><span>{formatTime(source.source.duration_ms)}</span></div><MediaPlayback key={source.media_url} url={source.media_url} title={source.source.title} hasVideo={!!hasVideo} audioRef={audioRef} videoRef={videoRef} /><div className="player-caption"><AudioLines size={16} />Click a transcript timestamp to seek to that point.</div></div> : source?.media_status === 'missing' ? <div className="fixture-banner notice--error" role="alert"><CircleAlert size={17} /><span>Original recording is missing. Re-upload the same file in the source library to restore playback and clip rendering.</span></div> : <div className="fixture-banner"><FileText size={17} /><span>Transcript-only source. Timing was supplied with the text; no playable audio or measured alignment is available.</span></div>}
    {segments.length ? <div className="source-timeline"><div><span>TRANSCRIPT SPANS</span><span>{formatTime(timelineDuration)}</span></div><svg viewBox="0 0 600 36" role="img" aria-label="Transcript span positions"><line x1="0" y1="18" x2="600" y2="18" className="timeline-track" />{segments.map((segment) => { const duration = timelineDuration; return <rect key={segment.id} x={segment.start_ms / duration * 600} y={selectedSegmentId === segment.id ? 6 : 11} width={Math.max(2, (segment.end_ms - segment.start_ms) / duration * 600 - 3)} height={selectedSegmentId === segment.id ? 24 : 14} rx="2" className={selectedSegmentId === segment.id ? 'timeline-span timeline-span--selected' : 'timeline-span'} /> })}</svg><p>{source?.media_url ? 'Select a timestamp below to seek the recording.' : 'Supplied transcript timing · audio alignment unverified.'}</p></div> : null}
    <div className="source-tabs" role="tablist" aria-label="Source information"><button role="tab" aria-selected={tab === 'transcript'} className={tab === 'transcript' ? 'active' : ''} onClick={() => setTab('transcript')}>Transcript <span>{segments.length}</span></button><button role="tab" aria-selected={tab === 'claims'} className={tab === 'claims' ? 'active' : ''} onClick={() => setTab('claims')}>Claim ledger <span>{claims.length}</span></button></div>
    {isPending ? <div className="source-loading">Loading source…</div> : !source ? <EmptyState title="No source selected">Choose a source from the library.</EmptyState> : tab === 'transcript' ? <div className="transcript-wrap"><div className="transcript-meta"><span>TRANSCRIPT · VERSION {source.transcript?.version ?? '—'}</span><span>{segments.length} SEGMENTS</span></div>{segments.length === 0 ? <EmptyState title="Transcript pending">The transcription workflow has not delivered any segments yet.</EmptyState> : <div className="transcript-list">{segments.map((segment) => <div id={`segment-${segment.id}`} className={`transcript-segment ${selectedSegmentId === segment.id ? 'transcript-segment--selected' : ''}`} key={segment.id}><button className="segment-time" onClick={() => select(segment)} title={`Seek to ${formatTime(segment.start_ms)}`}><span>{formatTime(segment.start_ms)}</span><Play size={11} fill="currentColor" /></button><div className="segment-content"><div className="segment-top"><span className="speaker-name">{segment.speaker || 'Speaker unspecified'}</span>{canEdit && editingId !== segment.id ? <button className="segment-edit" onClick={() => { setEditingId(segment.id); setDraftText(segment.text) }} title="Correct this transcript segment" aria-label={`Correct segment at ${formatTime(segment.start_ms)}`}><PenLine size={14} /></button> : null}</div>{editingId === segment.id ? <form onSubmit={(event) => { event.preventDefault(); if (draftText.trim() && draftText.trim() !== segment.text) save.mutate({ segmentId: segment.id, text: draftText.trim() }); else setEditingId(null) }}><textarea value={draftText} onChange={(event) => setDraftText(event.target.value)} aria-label="Corrected transcript text" rows={4} required /><div className="segment-edit-actions"><Button type="submit" variant="dark" loading={save.isPending}><Save size={14} />Save correction</Button><Button type="button" variant="text" onClick={() => setEditingId(null)}><X size={14} />Cancel</Button></div>{save.isError ? <div className="form-error" role="alert"><CircleAlert size={14} />{errorMessage(save.error)}</div> : null}</form> : <button className="segment-text" onClick={() => select(segment)}>{segment.text}</button>}</div></div>)}</div>}</div> : <div className="claims-wrap"><div className="claims-intro"><Quote size={20} /><p>Claims below are linked to transcript segments. Selecting one jumps to its source. Verification status is a workflow result, not a replacement for editorial judgment.</p></div>{claims.length === 0 ? <EmptyState icon={<Link2 size={24} />} title="No claim ledger yet">Claims will appear after a content batch is analyzed.</EmptyState> : <div className="claim-list">{claims.map((claim, index) => <button className="claim-item" key={claim.id} onClick={() => selectClaim(claim)} disabled={claim.source_segment_ids.length === 0}><div className="claim-number">{String(index + 1).padStart(2, '0')}</div><div><div className="claim-top"><Badge tone={claim.verification_status === 'verified' ? 'green' : 'orange'}>{claim.verification_status === 'verified' ? <BadgeCheck size={13} /> : <CircleAlert size={13} />}{claim.verification_status.replace(/_/g, ' ')}</Badge><span>{claim.source_segment_ids.length} source span{claim.source_segment_ids.length === 1 ? '' : 's'}</span></div><p>{claim.text}</p>{claim.warning ? <small className="claim-warning">{claim.warning}</small> : null}</div><ArrowUpRight size={17} /></button>)}</div>}</div>}
    <div className="source-pane-foot"><span><Link2 size={15} /> SOURCE PROVENANCE</span><span>{source?.source.rights_status || 'Rights status unavailable'}</span></div>
  </section>
}
