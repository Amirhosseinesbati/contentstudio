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
    return status === 'complete' || status === 'completed' || status === 'failed' ? false : 2500
  } })
  useEffect(() => {
    const stream = new EventSource(api.jobEventsUrl(jobId), { withCredentials: true })
    stream.onmessage = () => { void queryClient.invalidateQueries({ queryKey: ['job', jobId] }) }
    stream.onerror = () => { stream.close() }
    return () => stream.close()
  }, [jobId, queryClient])
  useEffect(() => {
    if ((query.data?.status === 'complete' || query.data?.status === 'completed') && completedJob.current !== jobId) {
      completedJob.current = jobId
      onComplete?.()
    }
  }, [jobId, query.data?.status, onComplete])

  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} title={`${label} status unavailable`} />
  const job = query.data
  const failed = job?.status === 'failed'
  const complete = job?.status === 'complete' || job?.status === 'completed'
  return <div className={`job-progress ${failed ? 'job-progress--failed' : ''}`} role="status">
    {failed ? <CircleAlert size={18} /> : complete ? <CheckCircle2 size={18} /> : <LoaderCircle size={18} className="spin" />}
    <div><strong>{label}: {job?.status?.replace(/_/g, ' ') ?? 'starting'}</strong>
      {failed ? <p>{job?.error || 'The job failed. You can retry from the asset.'}</p> : null}
      {!failed && !complete ? <p>Progress is read from the server. You can leave this view and return later.</p> : null}
    </div>
    {typeof job?.progress === 'number' ? <span>{Math.round(job.progress)}%</span> : null}
  </div>
}
