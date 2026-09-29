import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, CalendarDays, CircleDashed, Clock3, Inbox, Send } from 'lucide-react'
import { api } from '../api'
import { Badge, EmptyState, ErrorNotice } from '../components/Common'
import { formatDate, statusLabel } from '../utils'

export function Calendar({ onOpen }: { onOpen: (batchId: string, assetId?: string) => void }) {
  const query = useQuery({ queryKey: ['calendar'], queryFn: api.calendar })
  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} title="Calendar unavailable" />
  if (query.isPending) return <div className="loading-section"><CircleDashed size={22} className="spin" />Loading publication drafts…</div>
  const items = query.data.items
  return <div className="calendar-page page-enter"><div className="page-heading"><div><span className="eyebrow eyebrow--orange">DISTRIBUTION / CALENDAR</span><h1>Ready when you are.</h1><p>Publication-ready drafts and scheduled slots are shown here. Nothing is posted publicly from this desk.</p></div><div className="calendar-heading-icon"><CalendarDays size={39} strokeWidth={1.2} /></div></div>
    <div className="calendar-summary"><div><span className="eyebrow">EDITORIAL QUEUE</span><strong>{items.length}</strong><span>draft{items.length === 1 ? '' : 's'} in view</span></div><div><span className="eyebrow">NEXT STEP</span><strong className="summary-text">Review · draft · schedule</strong><span>Publishing remains a human decision</span></div><div className="summary-icon"><Send size={33} strokeWidth={1.2} /></div></div>
    <div className="calendar-list"><div className="calendar-list-head"><span>PUBLICATION DRAFT</span><span>CHANNEL</span><span>DATE</span><span>STATE</span></div>{items.length === 0 ? <EmptyState icon={<Inbox size={25} />} title="No publication drafts yet">Approved assets appear here when the scheduling workflow creates drafts. Check your n8n connection if you expected one.</EmptyState> : items.map((item) => <button className="calendar-row" key={item.id} onClick={() => item.batch_id && onOpen(item.batch_id, item.asset_version_id)} disabled={!item.batch_id} title={!item.batch_id ? 'This draft has no linked batch' : undefined}><span className="calendar-title"><span className="calendar-doc-icon"><Clock3 size={17} /></span><span><strong>{item.title || `Draft ${item.id.slice(0, 8)}`}</strong><small>{item.batch_id ? `From batch ${item.batch_id.slice(0, 8)}` : 'No linked batch'}</small></span></span><span>{item.channel || 'Editorial'}</span><span>{formatDate(item.scheduled_at)}</span><span><Badge tone={item.status === 'ready' ? 'green' : 'orange'}>{statusLabel(item.status || 'draft')}</Badge><ArrowUpRight size={16} /></span></button>)}</div>
    <div className="calendar-note"><CalendarDays size={19} /><p>Calendar entries come from saved publication drafts. A date shown here is a plan, not evidence of delivery or reach.</p></div>
  </div>
}
