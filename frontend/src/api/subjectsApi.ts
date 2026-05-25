import { apiRequest } from './client'
import type { AuthorizedSubject, CreateSubjectInput, CreatedSubjectResponse, MriCase } from '../types/api'

export function listSubjects(): Promise<AuthorizedSubject[]> {
  return apiRequest<AuthorizedSubject[]>('/subjects')
}

export function createSubject(input: CreateSubjectInput): Promise<CreatedSubjectResponse> {
  return apiRequest<CreatedSubjectResponse>('/subjects', {
    method: 'POST',
    body: input,
  })
}

export function listSubjectCases(subjectId: string): Promise<MriCase[]> {
  return apiRequest<MriCase[]>(`/subjects/${encodeURIComponent(subjectId)}/cases`)
}
