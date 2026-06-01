import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Job } from '../types/api'

type JobsByCase = Record<number, Job>

type JobActivityContextValue = {
  trackedJobs: JobsByCase
  getTrackedJobForCase: (caseId: number) => Job | null
  trackJob: (job: Job) => void
  clearCaseJob: (caseId: number) => void
  clearAllTrackedJobs: () => void
}

const JobActivityContext = createContext<JobActivityContextValue | null>(null)

function isTrackableCaseJob(job: Job): job is Job & { case_id: number } {
  return typeof job.case_id === 'number'
}

export function JobActivityProvider({ children }: { children: ReactNode }) {
  const [trackedJobs, setTrackedJobs] = useState<JobsByCase>({})

  const getTrackedJobForCase = useCallback(
    (caseId: number) => trackedJobs[caseId] ?? null,
    [trackedJobs],
  )

  const trackJob = useCallback((job: Job) => {
    if (!isTrackableCaseJob(job)) {
      return
    }

    setTrackedJobs((current) => {
      const previous = current[job.case_id]
      if (previous?.id === job.id && previous.status === job.status && previous.progress === job.progress && previous.message === job.message) {
        return current
      }
      return {
        ...current,
        [job.case_id]: job,
      }
    })
  }, [])

  const clearCaseJob = useCallback((caseId: number) => {
    setTrackedJobs((current) => {
      if (!(caseId in current)) {
        return current
      }
      const next = { ...current }
      delete next[caseId]
      return next
    })
  }, [])

  const clearAllTrackedJobs = useCallback(() => {
    setTrackedJobs({})
  }, [])

  const value = useMemo<JobActivityContextValue>(
    () => ({
      trackedJobs,
      getTrackedJobForCase,
      trackJob,
      clearCaseJob,
      clearAllTrackedJobs,
    }),
    [clearAllTrackedJobs, clearCaseJob, getTrackedJobForCase, trackJob, trackedJobs],
  )

  return <JobActivityContext.Provider value={value}>{children}</JobActivityContext.Provider>
}

export function useJobActivity() {
  const value = useContext(JobActivityContext)
  if (!value) {
    throw new Error('useJobActivity must be used inside JobActivityProvider')
  }
  return value
}
