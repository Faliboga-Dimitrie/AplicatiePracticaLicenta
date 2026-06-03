import type { MriCase } from '../types/api'

export type CaseStepKey = 'uploaded' | 'prepared' | 'modelled' | 'measured'

export type CaseStep = {
  key: CaseStepKey
  title: string
  description: string
  complete: boolean
}

export function formatDateLabel(date: string | null | undefined): string {
  if (!date) return 'No date set'
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return date
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(parsed)
}

export function formatSubjectName(subject: { id: string; name?: string | null }): string {
  return subject.name?.trim() ? subject.name : subject.id
}

export function formatCaseName(mriCase: MriCase): string {
  return `MRI scan from ${formatDateLabel(mriCase.acquisition_date)}`
}

export function getCaseSteps(mriCase: MriCase): CaseStep[] {
  const capabilities = mriCase.capabilities
  return [
    {
      key: 'uploaded',
      title: 'MRI uploaded',
      description: 'The original scan is available.',
      complete: Boolean(capabilities.raw_uploaded),
    },
    {
      key: 'prepared',
      title: 'Scan prepared',
      description: 'The brain has been isolated and tissue probabilities are ready.',
      complete: Boolean(capabilities.has_fast_pve_outputs),
    },
    {
      key: 'modelled',
      title: '3D model ready',
      description: 'The brain tissues can be opened in the 3D viewer.',
      complete: Boolean(capabilities.has_meshes || capabilities.can_view_meshes),
    },
    {
      key: 'measured',
      title: 'Measurements ready',
      description: 'Volume and surface measurements can be reviewed.',
      complete: Boolean(capabilities.has_metrics || capabilities.can_view_metrics),
    },
  ]
}

export function getCaseCompletion(mriCase: MriCase): number {
  const steps = getCaseSteps(mriCase)
  return Math.round((steps.filter((step) => step.complete).length / steps.length) * 100)
}

export function getCaseStageLabel(mriCase: MriCase): string {
  if (mriCase.capabilities.is_busy) return 'Processing now'
  if (mriCase.capabilities.can_view_metrics || mriCase.capabilities.has_metrics) return 'Ready for review'
  if (mriCase.capabilities.can_view_meshes || mriCase.capabilities.has_meshes) return '3D model ready'
  if (mriCase.capabilities.has_fast_pve_outputs) return 'Prepared for 3D model'
  if (mriCase.capabilities.raw_uploaded) return 'Ready to prepare'
  return 'Needs MRI upload'
}

export function getNextCaseAction(mriCase: MriCase): string {
  if (mriCase.capabilities.is_busy) return 'Processing is in progress. You can leave this page and come back later.'
  if (mriCase.capabilities.can_start_preprocessing || mriCase.capabilities.can_start_mesh_analysis) return 'Process this MRI scan to create the 3D model and measurements.'
  if (mriCase.capabilities.can_view_metrics || mriCase.capabilities.has_metrics) return 'Open the 3D model, review measurements, or compare this subject over time.'
  if (mriCase.capabilities.can_view_meshes || mriCase.capabilities.has_meshes) return 'Open the 3D model or review the generated files.'
  return 'Upload or refresh the case, then continue processing.'
}

export function friendlyJobTitle(type: string): string {
  const lower = type.toLowerCase()
  if (lower.includes('full') || lower.includes('processing')) return 'Processing MRI scan'
  if (lower.includes('preprocess')) return 'Preparing MRI scan'
  if (lower.includes('mesh') || lower.includes('analysis')) return 'Creating 3D model and measurements'
  return 'Processing MRI scan'
}

export function friendlyJobStatus(status: string): string {
  switch (status) {
    case 'queued':
      return 'Waiting to start'
    case 'running':
      return 'Running'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Needs attention'
    case 'cancellation_requested':
      return 'Stopping'
    case 'cancelled':
      return 'Stopped'
    default:
      return status.replaceAll('_', ' ')
  }
}
