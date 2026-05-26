import { apiPublicDownload } from './client'

export function processPublicMri(file: File): Promise<Blob> {
  const formData = new FormData()
  formData.append('file', file)
  return apiPublicDownload('/public/process', {
    method: 'POST',
    formData,
  })
}
