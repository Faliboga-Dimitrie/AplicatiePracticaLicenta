import { apiDownload, apiRequest } from './client'
import type { Artifact, CaseArtifacts } from '../types/api'
import { downloadBlob } from '../utils/downloads'

export function listArtifacts(caseId: number): Promise<CaseArtifacts> {
  return apiRequest<CaseArtifacts>(`/cases/${caseId}/artifacts`)
}

export function listViewerArtifacts(caseId: number): Promise<CaseArtifacts> {
  return apiRequest<CaseArtifacts>(`/cases/${caseId}/viewer-artifacts`)
}

export async function downloadArtifact(artifact: Artifact): Promise<void> {
  const blob = await apiDownload(artifact.url)
  downloadBlob(blob, artifact.name)
}

export async function createArtifactObjectUrl(artifact: Artifact): Promise<string> {
  const blob = await apiDownload(artifact.url)
  return URL.createObjectURL(blob)
}
