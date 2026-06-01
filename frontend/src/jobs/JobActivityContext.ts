import { createContext } from 'react'
import type { Job } from '../types/api'

export type JobsByCase = Record<number, Job>

export type JobActivityContextValue = {
  trackedJobs: JobsByCase
  getTrackedJobForCase: (caseId: number) => Job | null
  trackJob: (job: Job) => void
  clearCaseJob: (caseId: number) => void
  clearAllTrackedJobs: () => void
}

export const JobActivityContext = createContext<JobActivityContextValue | null>(null)
