import { apiRequest } from './client'
import type { Job } from '../types/api'

export function listJobs(caseId?: number): Promise<Job[]> {
  const query = caseId === undefined ? '' : `?case_id=${caseId}`
  return apiRequest<Job[]>(`/jobs${query}`)
}

export function getJob(jobId: string): Promise<Job> {
  return apiRequest<Job>(`/jobs/${encodeURIComponent(jobId)}`)
}

export function cancelJob(jobId: string): Promise<Job> {
  return apiRequest<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

export function startPreprocessingJob(caseId: number): Promise<Job> {
  return apiRequest<Job>(`/processing/cases/${caseId}/preprocessing-jobs`, {
    method: 'POST',
  })
}

export type MeshAnalysisJobOptions = {
  createWireframeSource?: boolean
  wireframeStepSize?: number | null
}

export function startMeshAnalysisJob(caseId: number, options: MeshAnalysisJobOptions = {}): Promise<Job> {
  return apiRequest<Job>(`/processing/cases/${caseId}/mesh-analysis-jobs`, {
    method: 'POST',
    body: {
      create_wireframe_source: options.createWireframeSource ?? true,
      wireframe_step_size: options.createWireframeSource === false ? null : options.wireframeStepSize ?? 3,
    },
  })
}
