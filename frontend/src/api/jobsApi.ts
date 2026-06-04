import { apiRequest } from './client'
import type { Job } from '../types/api'

export function getJob(jobId: string): Promise<Job> {
  return apiRequest<Job>(`/jobs/${encodeURIComponent(jobId)}`)
}

export function cancelJob(jobId: string): Promise<Job> {
  return apiRequest<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

export function startProcessingJob(caseId: number): Promise<Job> {
  return apiRequest<Job>(`/processing/cases/${caseId}/processing-jobs`, {
    method: 'POST',
  })
}
