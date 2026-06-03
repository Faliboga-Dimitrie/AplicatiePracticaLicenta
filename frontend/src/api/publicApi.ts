import JSZip from 'jszip'
import { apiPublicDownload, apiRequest } from './client'
import {
  inferViewerModeFromName,
  inferViewerTissueFromName,
  isGlbName,
} from '../components/brainViewerUtils'
import type { BrainViewerItem } from '../components/brainViewerUtils'
import type { PublicProcessingJob } from '../types/api'

export function startPublicProcessingJob(file: File): Promise<PublicProcessingJob> {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest<PublicProcessingJob>('/public/process-jobs', {
    method: 'POST',
    formData,
    auth: false,
  })
}

export function getPublicProcessingJob(jobId: string): Promise<PublicProcessingJob> {
  return apiRequest<PublicProcessingJob>(`/public/process-jobs/${encodeURIComponent(jobId)}`, {
    auth: false,
  })
}

export function downloadPublicProcessingResult(jobId: string): Promise<Blob> {
  return apiPublicDownload(`/public/process-jobs/${encodeURIComponent(jobId)}/download`)
}

export function processPublicMri(file: File): Promise<Blob> {
  const formData = new FormData()
  formData.append('file', file)
  return apiPublicDownload('/public/process', {
    method: 'POST',
    formData,
  })
}

export async function extractViewerItemsFromPublicZip(zipBlob: Blob): Promise<BrainViewerItem[]> {
  const zip = await JSZip.loadAsync(zipBlob)
  const items: BrainViewerItem[] = []

  for (const [path, entry] of Object.entries(zip.files)) {
    if (entry.dir || !isGlbName(path)) {
      continue
    }

    const mode = inferViewerModeFromName(path)
    const tissue = inferViewerTissueFromName(path)
    if (!mode || !tissue) {
      continue
    }

    const blob = await entry.async('blob')
    const objectUrl = URL.createObjectURL(new Blob([blob], { type: 'model/gltf-binary' }))
    items.push({
      id: `public-${mode}-${tissue}-${path}`,
      name: path.split('/').pop() ?? path,
      tissue,
      mode,
      objectUrl,
    })
  }

  return items
}
