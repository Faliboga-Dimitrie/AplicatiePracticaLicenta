import JSZip from 'jszip'
import { apiPublicDownload } from './client'
import {
  inferViewerModeFromName,
  inferViewerTissueFromName,
  isGlbName,
} from '../components/Brain3DViewer'
import type { BrainViewerItem } from '../components/Brain3DViewer'

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
