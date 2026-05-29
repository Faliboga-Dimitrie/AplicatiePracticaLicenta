import { apiDownload, apiRequest } from './client'
import type { Artifact, CaseArtifacts } from '../types/api'

export function listArtifacts(caseId: number): Promise<CaseArtifacts> {
  return apiRequest<CaseArtifacts>(`/cases/${caseId}/artifacts`)
}

export function listViewerArtifacts(caseId: number): Promise<CaseArtifacts> {
  return apiRequest<CaseArtifacts>(`/cases/${caseId}/viewer-artifacts`)
}

export async function downloadArtifact(artifact: Artifact): Promise<void> {
  const blob = await apiDownload(artifact.url)
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = artifact.name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function createArtifactObjectUrl(artifact: Artifact): Promise<string> {
  const blob = await apiDownload(artifact.url)
  return URL.createObjectURL(blob)
}
