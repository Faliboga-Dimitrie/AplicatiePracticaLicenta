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

export type Subject = {
  id: string
  name: string | null
  age: number | null
  notes: string | null
}

export type AuthorizedSubject = Subject & {
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

export type UpdateSubjectInput = {
  name?: string | null
  age?: number | null
  notes?: string | null
}

export type UpdateCaseInput = {
  acquisition_date?: string | null
  notes?: string | null
  status?: string | null
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
export type UpdatedCaseResponse = MutationResponse<'updated', { case: MriCase }>
export type DeletedCaseResponse = MutationResponse<'deleted', { case: MriCase }>
export type CreatedSubjectResponse = AuthorizedSubject
export type UpdatedSubjectResponse = MutationResponse<'updated', { subject: Subject }>
export type DeletedSubjectResponse = { deleted: boolean; subject_id: string }

export type TissueKey = 'csf' | 'gm' | 'wm'

export type CaseMetricValues = {
  csf_mm3?: number
  gm_mm3?: number
  wm_mm3?: number
  csf_mm2?: number
  gm_mm2?: number
  wm_mm2?: number
  [key: string]: number | undefined
}

export type CaseMetricsResponse = {
  case_id: number
  case_key: string | null
  subject_id: string
  acquisition_date: string
  status: string | null
  volumes: Record<string, number>
  surfaces: Record<string, number>
  totals: {
    volume_mm3: number
    surface_mm2: number
  }
  raw?: Record<string, unknown>
}

export type EvolutionDateEntry = {
  case_id: number
  acquisition_date: string
  status: string | null
  ready_for_json: boolean
  ready_for_visual: boolean
  has_metrics: boolean
  has_meshes: boolean
  has_wireframes: boolean
}

export type EvolutionDatesResponse = {
  subject_id: string
  dates: EvolutionDateEntry[]
}

export type EvolutionMetricComparison = {
  value: number
  baseline_value: number
  absolute_change_from_baseline: number
  ratio_to_baseline_percent: number | null
  change_from_baseline_percent: number | null
  previous_value: number | null
  absolute_change_from_previous: number | null
  ratio_to_previous_percent: number | null
  change_from_previous_percent: number | null
}

export type EvolutionPoint = {
  index: number
  acquisition_date: string
  is_baseline: boolean
  compared_to_baseline_date: string
  compared_to_previous_date: string | null
  volumes_mm3: Record<TissueKey, EvolutionMetricComparison>
  surfaces_mm2: Record<TissueKey, EvolutionMetricComparison>
}

export type BasicStats = {
  count: number
  min: number | null
  max: number | null
  mean: number | null
  median: number | null
  std_dev: number | null
}

export type EvolutionReport = {
  subject_id: string
  start_date: string
  end_date: string
  baseline_date: string
  dates: string[]
  baseline_values: {
    volumes_mm3: Record<TissueKey, number>
    surfaces_mm2: Record<TissueKey, number>
  }
  points: EvolutionPoint[]
  statistics: Record<string, Record<TissueKey, Record<string, BasicStats>>>
  notes?: Record<string, string>
}
