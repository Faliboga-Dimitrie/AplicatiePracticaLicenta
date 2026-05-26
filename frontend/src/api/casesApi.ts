import { apiRequest } from './client'
import type { CreatedCaseResponse, DeletedCaseResponse, MriCase, UpdateCaseInput, UpdatedCaseResponse } from '../types/api'

export function getCase(caseId: number): Promise<MriCase> {
  return apiRequest<MriCase>(`/cases/${caseId}`)
}

export function updateCase(caseId: number, input: UpdateCaseInput): Promise<UpdatedCaseResponse> {
  return apiRequest<UpdatedCaseResponse>(`/cases/${caseId}`, {
    method: 'PUT',
    body: input,
  })
}

export function deleteCase(caseId: number): Promise<DeletedCaseResponse> {
  return apiRequest<DeletedCaseResponse>(`/cases/${caseId}`, {
    method: 'DELETE',
  })
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
