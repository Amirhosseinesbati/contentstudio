import type { ReactNode } from 'react'
import { AlertTriangle, ArrowRight, Check, CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react'
import { errorMessage } from '../utils'

export function Button({ children, variant = 'dark', className = '', loading = false, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'dark' | 'light' | 'outline' | 'text' | 'orange'; loading?: boolean }) {
  return <button className={`button button--${variant} ${className}`} {...props} disabled={props.disabled || loading}>{loading ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : null}{children}</button>
}

export function Label({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className="form-label" {...props}>{children}</label>
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'orange' | 'green' | 'red' | 'blue' }) {
  return <span className={`badge badge--${tone}`}>{children}</span>
}

export function ErrorNotice({ error, onRetry, title = 'Could not load this section' }: { error: unknown; onRetry?: () => void; title?: string }) {
  return <div className="notice notice--error" role="alert"><CircleAlert size={19} aria-hidden="true" /><div><strong>{title}</strong><p>{errorMessage(error)}</p></div>{onRetry ? <Button variant="outline" onClick={onRetry}><RefreshCw size={15} /> Retry</Button> : null}</div>
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon ?? <AlertTriangle size={22} />}</div><h3>{title}</h3><p>{children}</p>{action}</div>
}

export function SectionHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) {
  return <div className="section-heading"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{action}</div>
}

export function InlineSuccess({ children }: { children: ReactNode }) {
  return <div className="inline-success" role="status"><Check size={16} aria-hidden="true" />{children}</div>
}

export function Notice({ children, tone = 'orange' }: { children: ReactNode; tone?: 'orange' | 'neutral' }) {
  return <div className={`notice notice--${tone}`}><ArrowRight size={17} aria-hidden="true" /><div>{children}</div></div>
}
