import { useEffect, useMemo, useRef, useState } from 'react'
import { apiMessage } from '../api/client'
import { cancelJob, getJob } from '../api/jobsApi'
import type { Job } from '../types/api'
import { friendlyJobStatus, friendlyJobTitle } from '../utils/userFacing'

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

type JobStatusCardProps = {
  initialJob: Job
  onJobChanged?: (job: Job) => void
  onFinished?: (job: Job) => void
}

export function JobStatusCard({ initialJob, onJobChanged, onFinished }: JobStatusCardProps) {
  const [job, setJob] = useState(initialJob)
  const [error, setError] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const notifiedFinishedJobId = useRef<string | null>(null)

  const isTerminal = TERMINAL_STATUSES.has(job.status)
  const progress = job.progress ?? 0
  const progressLabel = useMemo(() => `${Math.round(progress)}%`, [progress])
  const statusLabel = friendlyJobStatus(job.status)

  useEffect(() => {
    setJob(initialJob)
    setError(null)
    if (notifiedFinishedJobId.current !== initialJob.id) {
      notifiedFinishedJobId.current = null
    }
  }, [initialJob])

  useEffect(() => {
    onJobChanged?.(job)
  }, [job, onJobChanged])

  useEffect(() => {
    if (!isTerminal) return undefined

    if (notifiedFinishedJobId.current !== job.id) {
      notifiedFinishedJobId.current = job.id
      onFinished?.(job)
    }

    return undefined
  }, [isTerminal, job, onFinished])

  useEffect(() => {
    if (isTerminal) return undefined

    let stopped = false
    const jobId = job.id

    const poll = async () => {
      try {
        const freshJob = await getJob(jobId)
        if (!stopped) {
          setJob(freshJob)
          setError(null)
        }
      } catch (pollError) {
        if (!stopped) setError(apiMessage(pollError))
      }
    }

    const interval = window.setInterval(poll, 3000)

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
          <p className="eyebrow">Processing</p>
          <h3>{friendlyJobTitle(job.type)}</h3>
        </div>
        <span className={`badge badge-${job.status}`}>{statusLabel}</span>
      </div>

      <div className="progress-wrap" aria-label={progressLabel}>
        <div className="progress-bar" style={{ width: `${progress}%` }} />
      </div>
      <p>{job.message || (isTerminal ? statusLabel : 'Working on this scan...')}</p>
      {job.error && <p className="error-text">{job.error}</p>}
      {error && <p className="error-text">{error}</p>}

      {!isTerminal && (
        <button type="button" className="secondary" onClick={handleCancel} disabled={isCancelling}>
          {isCancelling ? 'Stopping...' : 'Stop processing'}
        </button>
      )}
    </article>
  )
}
