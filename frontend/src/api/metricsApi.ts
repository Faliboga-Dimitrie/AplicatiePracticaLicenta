import { apiDownload, apiRequest } from './client'
import type { CaseMetricsResponse, EvolutionDatesResponse, EvolutionReport, TissueKey } from '../types/api'

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

export function getEvolutionVisualComparisonGlb(
  subjectId: string,
  startDate: string,
  endDate: string,
  options: { targetDate?: string; tissues?: TissueKey[]; includeWireframes?: boolean } = {},
): Promise<Blob> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    include_wireframes: String(options.includeWireframes ?? true),
  })

  if (options.targetDate) {
    params.set('target_date', options.targetDate)
  }

  for (const tissue of options.tissues ?? []) {
    params.append('tissues', tissue)
  }

  return apiDownload(`/processing/subjects/${encodeURIComponent(subjectId)}/evolution/visual?${params}`)
}
