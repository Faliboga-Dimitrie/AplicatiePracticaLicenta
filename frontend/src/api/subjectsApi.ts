import { apiRequest } from './client'
import type {
  AuthorizedSubject,
  CreateSubjectInput,
  CreatedSubjectResponse,
  DeletedSubjectResponse,
  MriCase,
  UpdateSubjectInput,
  UpdatedSubjectResponse,
} from '../types/api'

export function listSubjects(): Promise<AuthorizedSubject[]> {
  return apiRequest<AuthorizedSubject[]>('/subjects')
}

export function createSubject(input: CreateSubjectInput): Promise<CreatedSubjectResponse> {
  return apiRequest<CreatedSubjectResponse>('/subjects', {
    method: 'POST',
    body: input,
  })
}

export function updateSubject(subjectId: string, input: UpdateSubjectInput): Promise<UpdatedSubjectResponse> {
  return apiRequest<UpdatedSubjectResponse>(`/subjects/${encodeURIComponent(subjectId)}`, {
    method: 'PUT',
    body: input,
  })
}

export function deleteSubject(subjectId: string): Promise<DeletedSubjectResponse> {
  return apiRequest<DeletedSubjectResponse>(`/subjects/${encodeURIComponent(subjectId)}`, {
    method: 'DELETE',
  })
}

export function listSubjectCases(subjectId: string): Promise<MriCase[]> {
  return apiRequest<MriCase[]>(`/subjects/${encodeURIComponent(subjectId)}/cases`)
}
