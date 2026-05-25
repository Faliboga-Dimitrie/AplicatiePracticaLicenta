import { apiRequest } from './client'
import type { CreatedCaseResponse, MriCase } from '../types/api'

export function getCase(caseId: number): Promise<MriCase> {
  return apiRequest<MriCase>(`/cases/${caseId}`)
}

export function uploadCase(input: {
  subjectId: string
  acquisitionDate: string
  notes?: string
  file: File
}): Promise<CreatedCaseResponse> {
  const formData = new FormData()
  formData.append('subject_id', input.subjectId)
  formData.append('acquisition_date', input.acquisitionDate)
  if (input.notes) {
    formData.append('notes', input.notes)
  }
  formData.append('file', input.file)

  return apiRequest<CreatedCaseResponse>('/cases/upload', {
    method: 'POST',
    formData,
  })
}
