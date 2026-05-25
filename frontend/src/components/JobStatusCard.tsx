import { useEffect, useMemo, useRef, useState } from 'react'
import { apiMessage } from '../api/client'
import { cancelJob, getJob } from '../api/jobsApi'
import type { Job } from '../types/api'

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

type JobStatusCardProps = {
  initialJob: Job
  onFinished?: (job: Job) => void
}

export function JobStatusCard({ initialJob, onFinished }: JobStatusCardProps) {
  const [job, setJob] = useState(initialJob)
  const [error, setError] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const finishedNotificationSentFor = useRef<string | null>(null)

  const isTerminal = TERMINAL_STATUSES.has(job.status)
  const progressLabel = useMemo(() => {
    if (job.progress === null || job.progress === undefined) {
      return 'Progress unavailable'
    }
    return `${Math.round(job.progress)}%`
  }, [job.progress])

  useEffect(() => {
    setJob(initialJob)
    finishedNotificationSentFor.current = null
  }, [initialJob])

  useEffect(() => {
    if (!isTerminal) {
      return
    }

    if (finishedNotificationSentFor.current === job.id) {
      return
    }

    finishedNotificationSentFor.current = job.id
    onFinished?.(job)
  }, [isTerminal, job, onFinished])

  useEffect(() => {
    if (isTerminal) {
      return undefined
    }

    let stopped = false
    const interval = window.setInterval(async () => {
      try {
        const freshJob = await getJob(job.id)
        if (!stopped) {
          setJob(freshJob)
          setError(null)
        }
      } catch (pollError) {
        if (!stopped) {
          setError(apiMessage(pollError))
        }
      }
    }, 3000)

    return () => {
      stopped = true
      window.clearInterval(interval)
    }
  }, [isTerminal, job.id])

  async function handleCancel() {
    setIsCancelling(true)
    setError(null)
    try {
      const cancelled = await cancelJob(job.id)
      setJob(cancelled)
    } catch (cancelError) {
      setError(apiMessage(cancelError))
    } finally {
      setIsCancelling(false)
    }
  }

  return (
    <article className="card job-card">
      <div className="row-between">
        <div>
          <h3>{job.type}</h3>
          <p className="muted">Job {job.id}</p>
        </div>
        <span className={`badge badge-${job.status}`}>{job.status}</span>
      </div>

      <div className="progress-wrap" aria-label={progressLabel}>
        <div className="progress-bar" style={{ width: `${job.progress ?? 0}%` }} />
      </div>
      <p>{job.message || 'No message yet.'}</p>
      {job.error && <p className="error-text">{job.error}</p>}
      {error && <p className="error-text">{error}</p>}

      {!isTerminal && (
        <button type="button" className="secondary" onClick={handleCancel} disabled={isCancelling}>
          {isCancelling ? 'Cancelling...' : 'Cancel job'}
        </button>
      )}
    </article>
  )
}
