export type User = {
  id: number
  email: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
  expires_at: string
  user: User
}

export type CurrentUserResponse = {
  user: User
}

export type ApiErrorPayload = {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

export type AuthorizedSubject = {
  id: string
  name: string | null
  age: number | null
  notes: string | null
  role: string
  case_count: number
  cases?: MriCase[] | null
}

export type CaseWorkspaceState = {
  case_id?: string | null
  subject_id?: string | null
  acquisition_date?: string | null
  exists?: boolean
  raw_exists?: boolean
  directories?: Record<string, boolean>
  outputs?: Record<string, boolean>
}

export type CaseCapabilities = {
  raw_uploaded?: boolean
  has_reoriented?: boolean
  has_skull_stripped?: boolean
  has_fast_outputs?: boolean
  has_fast_pve_outputs?: boolean
  has_meshes?: boolean
  has_wireframes?: boolean
  has_metrics?: boolean
  has_qc_images?: boolean
  can_start_preprocessing?: boolean
  can_start_mesh_analysis?: boolean
  can_view_artifacts?: boolean
  can_view_meshes?: boolean
  can_view_metrics?: boolean
  is_busy?: boolean
}

export type MriCase = {
  id: number
  subject_id: string
  acquisition_date: string
  notes: string | null
  status: string | null
  case_key: string | null
  workspace: CaseWorkspaceState | null
  capabilities: CaseCapabilities
}

export type CreateSubjectInput = {
  subject_id: string
  name?: string | null
  age?: number | null
  notes?: string | null
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancellation_requested'
  | 'cancelled'
  | string

export type Job = {
  id: string
  type: string
  status: JobStatus
  user_id: number
  case_id: number | null
  message: string | null
  progress: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  result: unknown | null
  error: string | null
  metadata: Record<string, unknown>
  cancel_requested: boolean
}

export type Artifact = {
  name: string
  kind: string
  url: string
  mime_type: string | null
  size_bytes: number
  metadata: Record<string, unknown>
}

export type CaseArtifacts = {
  case_id: number
  case_key: string
  subject_id: string
  acquisition_date: string
  artifacts: Artifact[]
}

export type MutationResponse<TName extends string, TPayload> = {
  [Key in TName]: boolean
} & TPayload

export type CreatedCaseResponse = MutationResponse<'created', { case: MriCase }>
export type CreatedSubjectResponse = AuthorizedSubject
export type DeletedResponse = { deleted: boolean }
