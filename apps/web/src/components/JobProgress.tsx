import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleAlert, LoaderCircle } from 'lucide-react'
import { api } from '../api'
import { ErrorNotice } from './Common'

export function JobProgress({ jobId, label, onComplete }: { jobId: string; label: string; onComplete?: () => void }) {
  const queryClient = useQueryClient()
  const completedJob = useRef<string | null>(null)
  const query = useQuery({ queryKey: ['job', jobId], queryFn: () => api.job(jobId), refetchInterval: (state) => {
    const status = state.state.data?.status
    return status && ['complete', 'completed', 'failed', 'cancelled', 'stale'].includes(status) ? false : 2500
  } })
  useEffect(() => {
    const stream = new EventSource(api.jobEventsUrl(jobId), { withCredentials: true })
    stream.onmessage = () => { void queryClient.invalidateQueries({ queryKey: ['job', jobId] }) }
    stream.onerror = () => { stream.close() }
    return () => stream.close()
  }, [jobId, queryClient])
  useEffect(() => {
    const completionKey = `${jobId}:${query.data?.updated_at ?? ''}`
    if ((query.data?.status === 'complete' || query.data?.status === 'completed') && completedJob.current !== completionKey) {
      completedJob.current = completionKey
      onComplete?.()
    }
  }, [jobId, query.data?.status, query.data?.updated_at, onComplete])

  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} title={`${label} status unavailable`} />
  const job = query.data
  const failed = job?.status === 'failed' || job?.status === 'stale' || job?.status === 'cancelled'
  const complete = job?.status === 'complete' || job?.status === 'completed'
  return <div className={`job-progress ${failed ? 'job-progress--failed' : ''}`} role="status">
    {failed ? <CircleAlert size={18} /> : complete ? <CheckCircle2 size={18} /> : <LoaderCircle size={18} className="spin" />}
    <div><strong>{label}: {job?.status?.replace(/_/g, ' ') ?? 'starting'}</strong>
      {failed ? <p>{job?.error || (job?.status === 'stale' ? 'Source or asset changed. Review the current version, then request a new operation.' : job?.status === 'cancelled' ? 'This queued operation was cancelled. Request it again to retry.' : 'The job failed. You can retry from the asset.')}</p> : null}
      {!failed && !complete ? <p>Progress is read from the server. You can leave this view and return later.</p> : null}
    </div>
    {typeof job?.progress === 'number' ? <span>{Math.round(job.progress)}%</span> : null}
  </div>
}
