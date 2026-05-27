import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { deleteCase, getCase, updateCase } from '../api/casesApi'
import { listArtifacts } from '../api/artifactsApi'
import { listJobs, startMeshAnalysisJob, startPreprocessingJob } from '../api/jobsApi'
import { ArtifactList } from '../components/ArtifactList'
import { JobStatusCard } from '../components/JobStatusCard'
import type { CaseArtifacts, Job, MriCase } from '../types/api'

type CaseDetailPageProps = {
  caseId: number
  onBack: () => void
}

type CaseEditorState = {
  acquisitionDate: string
  notes: string
  status: string
}

function capabilityText(value: boolean | undefined): string {
  return value ? 'yes' : 'no'
}

function isTerminalJob(job: Job): boolean {
  return ['completed', 'failed', 'cancelled'].includes(job.status)
}

function toCaseEditorState(mriCase: MriCase): CaseEditorState {
  return {
    acquisitionDate: mriCase.acquisition_date,
    notes: mriCase.notes ?? '',
    status: mriCase.status ?? '',
  }
}

export function CaseDetailPage({ caseId, onBack }: CaseDetailPageProps) {
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [caseDraft, setCaseDraft] = useState<CaseEditorState | null>(null)
  const [artifacts, setArtifacts] = useState<CaseArtifacts | null>(null)
  const [activeJob, setActiveJob] = useState<Job | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isStartingPreprocessing, setIsStartingPreprocessing] = useState(false)
  const [isStartingMesh, setIsStartingMesh] = useState(false)
  const [isUpdatingCase, setIsUpdatingCase] = useState(false)
  const [isDeletingCase, setIsDeletingCase] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshCase = useCallback(async () => {
    setError(null)
    const loadedCase = await getCase(caseId)
    setMriCase(loadedCase)
    return loadedCase
  }, [caseId])

  const refreshArtifacts = useCallback(async () => {
    setError(null)
    try {
      const loadedArtifacts = await listArtifacts(caseId)
      setArtifacts(loadedArtifacts)
    } catch (artifactError) {
      setArtifacts(null)
      setError(apiMessage(artifactError))
    }
  }, [caseId])

  const refreshActiveJob = useCallback(async () => {
    const jobs = await listJobs(caseId)
    const active = jobs.find((job) => !isTerminalJob(job)) ?? null
    setActiveJob(active)
    return active
  }, [caseId])

  const refreshAll = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      await refreshCase()
      await refreshArtifacts()
      await refreshActiveJob()
    } catch (loadError) {
      setError(apiMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [refreshActiveJob, refreshArtifacts, refreshCase])

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  async function handleStartPreprocessing() {
    setIsStartingPreprocessing(true)
    setError(null)
    try {
      const job = await startPreprocessingJob(caseId)
      setActiveJob(job)
      await refreshCase()
    } catch (startError) {
      setError(apiMessage(startError))
    } finally {
      setIsStartingPreprocessing(false)
    }
  }

  async function handleStartMeshAnalysis() {
    setIsStartingMesh(true)
    setError(null)
    try {
      const job = await startMeshAnalysisJob(caseId)
      setActiveJob(job)
      await refreshCase()
    } catch (startError) {
      setError(apiMessage(startError))
    } finally {
      setIsStartingMesh(false)
    }
  }

  const handleJobFinished = useCallback(async () => {
    await refreshAll()
  }, [refreshAll])

  async function handleUpdateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!caseDraft) {
      return
    }

    setIsUpdatingCase(true)
    setError(null)
    try {
      const response = await updateCase(caseId, {
        acquisition_date: caseDraft.acquisitionDate,
        notes: caseDraft.notes.trim() || null,
        status: caseDraft.status.trim() || null,
      })
      setMriCase(response.case)
      setCaseDraft(null)
      await refreshArtifacts()
    } catch (updateError) {
      setError(apiMessage(updateError))
    } finally {
      setIsUpdatingCase(false)
    }
  }

  async function handleDeleteCase() {
    if (!mriCase) {
      return
    }
    const confirmed = window.confirm(
      `Delete case #${mriCase.id} from ${mriCase.acquisition_date}? This deletes the database row and its local workspace files.`,
    )
    if (!confirmed) {
      return
    }

    setIsDeletingCase(true)
    setError(null)
    try {
      await deleteCase(mriCase.id)
      onBack()
    } catch (deleteError) {
      setError(apiMessage(deleteError))
    } finally {
      setIsDeletingCase(false)
    }
  }

  const capabilities = mriCase?.capabilities

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to cases</button>
          <p className="eyebrow">Case workspace</p>
          <h1>Case #{caseId}</h1>
          <p className="muted">Inspect metadata, start processing jobs, download artifacts, or edit/delete this case.</p>
        </div>
        <button type="button" className="secondary" onClick={refreshAll} disabled={isLoading}>
          Refresh
        </button>
      </section>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Loading case...</p>}

      {mriCase && (
        <section className="grid-two">
          <article className="card stack">
            <div className="row-between">
              <h2>Case details</h2>
              <span className="badge">{mriCase.status || 'no status'}</span>
            </div>
            <dl className="details-list">
              <div><dt>Subject</dt><dd>{mriCase.subject_id}</dd></div>
              <div><dt>Acquisition date</dt><dd>{mriCase.acquisition_date}</dd></div>
              <div><dt>Status</dt><dd>{mriCase.status || 'none'}</dd></div>
              <div><dt>Case key</dt><dd>{mriCase.case_key || 'none'}</dd></div>
              <div><dt>Notes</dt><dd>{mriCase.notes || 'none'}</dd></div>
            </dl>
            <div className="button-row">
              <button type="button" className="secondary" onClick={() => setCaseDraft(toCaseEditorState(mriCase))}>
                Edit metadata
              </button>
              <button type="button" className="danger-button" onClick={handleDeleteCase} disabled={isDeletingCase}>
                {isDeletingCase ? 'Deleting...' : 'Delete case'}
              </button>
            </div>
          </article>

          <article className="card stack">
            <h2>Capabilities</h2>
            <div className="capability-grid">
              <span>Raw uploaded</span><strong>{capabilityText(capabilities?.raw_uploaded)}</strong>
              <span>FAST outputs</span><strong>{capabilityText(capabilities?.has_fast_pve_outputs)}</strong>
              <span>Meshes</span><strong>{capabilityText(capabilities?.has_meshes)}</strong>
              <span>Metrics</span><strong>{capabilityText(capabilities?.has_metrics)}</strong>
              <span>Busy</span><strong>{capabilityText(capabilities?.is_busy)}</strong>
            </div>
          </article>
        </section>
      )}

      {caseDraft && (
        <form className="card form-grid" onSubmit={handleUpdateCase}>
          <div className="row-between">
            <div>
              <p className="eyebrow">Edit case</p>
              <h2>Metadata</h2>
            </div>
            <button type="button" className="secondary" onClick={() => setCaseDraft(null)}>
              Cancel
            </button>
          </div>
          <label>
            Acquisition date
            <input
              type="date"
              value={caseDraft.acquisitionDate}
              onChange={(event) => setCaseDraft({ ...caseDraft, acquisitionDate: event.target.value })}
              required
            />
          </label>
          <label>
            Status
            <select
              value={caseDraft.status}
              onChange={(event) => setCaseDraft({ ...caseDraft, status: event.target.value })}
            >
              <option value="">No status</option>
              <option value="registered">registered</option>
              <option value="preprocessing_queued">preprocessing_queued</option>
              <option value="preprocessing">preprocessing</option>
              <option value="preprocessed">preprocessed</option>
              <option value="mesh_queued">mesh_queued</option>
              <option value="mesh_analysis">mesh_analysis</option>
              <option value="mesh_completed">mesh_completed</option>
              <option value="failed">failed</option>
              <option value="preprocessing_cancelled">preprocessing_cancelled</option>
              <option value="mesh_cancelled">mesh_cancelled</option>
            </select>
          </label>
          <p className="muted small-note">Status is normally changed by backend jobs. Manual editing is mostly for correction/testing.</p>
          <label>
            Notes
            <textarea
              value={caseDraft.notes}
              onChange={(event) => setCaseDraft({ ...caseDraft, notes: event.target.value })}
              rows={4}
            />
          </label>
          <button type="submit" disabled={isUpdatingCase}>
            {isUpdatingCase ? 'Saving...' : 'Save case changes'}
          </button>
        </form>
      )}

      {mriCase && (
        <section className="card stack">
          <h2>Processing actions</h2>
          <div className="button-row">
            <button
              type="button"
              onClick={handleStartPreprocessing}
              disabled={!mriCase.capabilities.can_start_preprocessing || isStartingPreprocessing}
            >
              {isStartingPreprocessing ? 'Starting...' : 'Start preprocessing'}
            </button>
            <button
              type="button"
              onClick={handleStartMeshAnalysis}
              disabled={!mriCase.capabilities.can_start_mesh_analysis || isStartingMesh}
            >
              {isStartingMesh ? 'Starting...' : 'Start mesh analysis'}
            </button>
          </div>
          <p className="muted">
            Buttons are disabled when the backend says the case is not ready or is already busy.
          </p>
          <div className="button-row disabled-action-row">
            <button type="button" disabled>Open 3D view</button>
            <button type="button" disabled>Open statistics</button>
            <button type="button" disabled>Compare over time</button>
          </div>
        </section>
      )}

      {activeJob && <JobStatusCard initialJob={activeJob} onFinished={handleJobFinished} />}

      <section className="card stack">
        <div className="row-between">
          <h2>Artifacts</h2>
          <button type="button" className="secondary" onClick={refreshArtifacts}>
            Refresh artifacts
          </button>
        </div>
        <ArtifactList artifacts={artifacts?.artifacts ?? []} />
      </section>
    </main>
  )
}
