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

export type EvolutionComparisonMethod = 'pve' | 'nearest_distance'
export type EvolutionVisualMode = 'changed_unchanged' | 'changed_region_before_after'
export type EvolutionVisualStyle = 'binary' | 'statistical_heatmap'

export type EvolutionVisualOptions = {
  subjectId: string
  startDate: string
  endDate: string
  targetDate?: string
  tissue?: string
  comparisonMethod?: EvolutionComparisonMethod
  visualMode?: EvolutionVisualMode
  visualStyle?: EvolutionVisualStyle
  pveThreshold?: number
  distanceThresholdMm?: number
  baselineColor?: string
  changedColor?: string
  marchingCubesStepSize?: number
}

export async function createEvolutionVisualComparisonObjectUrl(options: EvolutionVisualOptions): Promise<string> {
  const params = new URLSearchParams({
    start_date: options.startDate,
    end_date: options.endDate,
    comparison_method: options.comparisonMethod ?? 'pve',
    visual_mode: options.visualMode ?? 'changed_unchanged',
    visual_style: options.visualStyle ?? 'binary',
    pve_threshold: String(options.pveThreshold ?? 0.3),
    distance_threshold_mm: String(options.distanceThresholdMm ?? 2),
    baseline_color: options.baselineColor ?? '#508cff',
    changed_color: options.changedColor ?? '#ff2d2d',
    marching_cubes_step_size: String(options.marchingCubesStepSize ?? 1),
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
