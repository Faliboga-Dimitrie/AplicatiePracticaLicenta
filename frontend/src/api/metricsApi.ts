import { apiDownload, apiRequest } from './client'
import type { CaseMetricsResponse, EvolutionDatesResponse, EvolutionReport } from '../types/api'

export function getCaseMetrics(caseId: number): Promise<CaseMetricsResponse> {
  return apiRequest<CaseMetricsResponse>(`/cases/${caseId}/metrics`)
}

export function listEvolutionDates(subjectId: string): Promise<EvolutionDatesResponse> {
  return apiRequest<EvolutionDatesResponse>(`/processing/subjects/${encodeURIComponent(subjectId)}/evolution/dates`)
}

export function getEvolutionReport(
  subjectId: string,
  startDate: string,
  endDate: string,
): Promise<EvolutionReport> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
  return apiRequest<EvolutionReport>(`/processing/subjects/${encodeURIComponent(subjectId)}/evolution?${params}`)
}

export type EvolutionVisualOptions = {
  subjectId: string
  startDate: string
  endDate: string
  targetDate?: string
  tissue?: string
  includeMeshes?: boolean
  includeWireframes?: boolean
}

export async function createEvolutionVisualComparisonObjectUrl(options: EvolutionVisualOptions): Promise<string> {
  const params = new URLSearchParams({
    start_date: options.startDate,
    end_date: options.endDate,
    include_meshes: String(options.includeMeshes ?? false),
    include_wireframes: String(options.includeWireframes ?? true),
  })

  if (options.targetDate) {
    params.set('target_date', options.targetDate)
  }
  if (options.tissue) {
    params.append('tissues', options.tissue)
  }

  const blob = await apiDownload(
    `/processing/subjects/${encodeURIComponent(options.subjectId)}/evolution/visual?${params.toString()}`,
  )
  return URL.createObjectURL(blob)
}
