import { apiRequest } from './client'
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
