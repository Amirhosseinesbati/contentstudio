import { Check, Circle, CircleAlert, FileCheck2, Link2, Package, ScanText } from 'lucide-react'
import type { BatchDetail, SourceDetail } from '../types'
import { packagePreflight } from './production'

export function ProductionPath({ batch, source }: { batch: BatchDetail; source?: SourceDetail }) {
  const preflight = packagePreflight(batch.assets)
  const waiting = batch.assets.filter((asset) => asset.status === 'review_pending').length
  const stages = [
    { label: 'Source evidence', value: `${source?.transcript?.segments.length ?? 0} transcript spans`, Icon: ScanText, complete: !!source?.transcript?.segments.length },
    { label: 'Content suite', value: `${batch.assets.length} working assets`, Icon: Link2, complete: !!batch.assets.length },
    { label: 'Editorial review', value: `${preflight.approved.length} approved · ${waiting} pending`, Icon: FileCheck2, complete: !!preflight.approved.length && !waiting },
    { label: 'Production handoff', value: preflight.ready ? 'Preflight ready · server verification required' : preflight.waitingForRender.length ? `${preflight.waitingForRender.length} media render(s) required` : 'Preflight blocked', Icon: Package, complete: preflight.ready },
  ]
  return <ol className="production-path" aria-label="Production readiness">
    {stages.map(({ label, value, Icon, complete }, index) => <li key={label} className={complete ? 'stage--ready' : ''}><span className="stage-icon"><Icon size={17} /></span><div><span className="stage-label">{String(index + 1).padStart(2, '0')} / {label}</span><strong>{value}</strong></div><span className="stage-state">{complete ? <Check size={14} aria-label="Complete" /> : index === 3 && preflight.waitingForRender.length ? <CircleAlert size={14} aria-label="Blocked" /> : <Circle size={12} aria-label="Pending" />}</span></li>)}
  </ol>
}
