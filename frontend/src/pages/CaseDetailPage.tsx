import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { deleteCase, getCase, updateCase } from '../api/casesApi'
import { listArtifacts } from '../api/artifactsApi'
import { startMeshAnalysisJob, startPreprocessingJob } from '../api/jobsApi'
import { ArtifactList } from '../components/ArtifactList'
import { CaseProgress } from '../components/CaseProgress'
import { JobStatusCard } from '../components/JobStatusCard'
import { useJobActivity } from '../jobs/useJobActivity'
import type { CaseArtifacts, Job, MriCase } from '../types/api'
import { formatCaseName, formatDateLabel, getCaseStageLabel, getNextCaseAction } from '../utils/userFacing'

type CaseDetailPageProps = {
  caseId: number
  onBack: () => void
  onOpenViewer: () => void
  onOpenStatistics: () => void
  onOpenTimeComparison: () => void
}

type CaseEditorState = {
  acquisitionDate: string
  notes: string
}

function toCaseEditorState(mriCase: MriCase): CaseEditorState {
  return {
    acquisitionDate: mriCase.acquisition_date,
    notes: mriCase.notes ?? '',
  }
}

function disabledHint(mriCase: MriCase, action: 'prepare' | 'model'): string {
  if (mriCase.capabilities.is_busy) return 'Processing is already running for this scan.'
  if (action === 'prepare') return 'This scan is already prepared or cannot be prepared yet.'
  return 'Prepare the scan first, then create the 3D model and measurements.'
}

export function CaseDetailPage({ caseId, onBack, onOpenViewer, onOpenStatistics, onOpenTimeComparison }: CaseDetailPageProps) {
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [caseDraft, setCaseDraft] = useState<CaseEditorState | null>(null)
  const [artifacts, setArtifacts] = useState<CaseArtifacts | null>(null)
  const { getTrackedJobForCase, trackJob, clearCaseJob } = useJobActivity()
  const [isLoading, setIsLoading] = useState(true)
  const [isStartingPreprocessing, setIsStartingPreprocessing] = useState(false)
  const [isStartingMesh, setIsStartingMesh] = useState(false)
  const [isUpdatingCase, setIsUpdatingCase] = useState(false)
  const [isDeletingCase, setIsDeletingCase] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const activeJob = getTrackedJobForCase(caseId)

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

  const refreshAll = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      await refreshCase()
      await refreshArtifacts()
    } catch (loadError) {
      setError(apiMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [refreshArtifacts, refreshCase])

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  async function handleStartPreprocessing() {
    setIsStartingPreprocessing(true)
    setError(null)
    try {
      const job = await startPreprocessingJob(caseId)
      trackJob(job)
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
      trackJob(job)
      await refreshCase()
    } catch (startError) {
      setError(apiMessage(startError))
    } finally {
      setIsStartingMesh(false)
    }
  }

  const handleJobFinished = useCallback(async () => {
    clearCaseJob(caseId)
    await refreshAll()
  }, [caseId, clearCaseJob, refreshAll])

  const handleJobUpdated = useCallback((job: Job) => {
    trackJob(job)
  }, [trackJob])

  async function handleUpdateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!caseDraft) return

    setIsUpdatingCase(true)
    setError(null)
    try {
      const response = await updateCase(caseId, {
        acquisition_date: caseDraft.acquisitionDate,
        notes: caseDraft.notes.trim() || null,
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
    if (!mriCase) return
    const confirmed = window.confirm(
      `Delete the MRI scan from ${formatDateLabel(mriCase.acquisition_date)}?`,
    )
    if (!confirmed) return

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

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to scans</button>
          <p className="eyebrow">MRI scan</p>
          <h1>{mriCase ? formatCaseName(mriCase) : 'MRI scan'}</h1>
          <p className="muted">Follow the guided steps, then open the visual and measurement results.</p>
        </div>
        <button type="button" className="secondary" onClick={refreshAll} disabled={isLoading}>
          Refresh
        </button>
      </section>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Loading scan...</p>}

      {mriCase && (
        <>
          <section className="grid-two">
            <article className="card stack scan-summary-card">
              <div className="row-between">
                <div>
                  <p className="eyebrow">Current state</p>
                  <h2>{getCaseStageLabel(mriCase)}</h2>
                </div>
                <span className="badge">{formatDateLabel(mriCase.acquisition_date)}</span>
              </div>
              <p className="muted">{getNextCaseAction(mriCase)}</p>
              <dl className="details-list clean-details-list">
                <div><dt>Subject</dt><dd>{mriCase.subject_id}</dd></div>
                <div><dt>Acquisition date</dt><dd>{formatDateLabel(mriCase.acquisition_date)}</dd></div>
                <div><dt>Notes</dt><dd>{mriCase.notes || 'No notes added.'}</dd></div>
              </dl>
              <div className="button-row">
                <button type="button" className="secondary" onClick={() => setCaseDraft(toCaseEditorState(mriCase))}>
                  Edit date/notes
                </button>
                <button type="button" className="danger-button" onClick={handleDeleteCase} disabled={isDeletingCase}>
                  {isDeletingCase ? 'Deleting...' : 'Delete scan'}
                </button>
              </div>
            </article>

            <article className="card stack">
              <p className="eyebrow">Progress</p>
              <h2>Processing checklist</h2>
              <CaseProgress mriCase={mriCase} />
            </article>
          </section>

          {caseDraft && (
            <form className="card form-grid" onSubmit={handleUpdateCase}>
              <div className="row-between">
                <div>
                  <p className="eyebrow">Edit scan</p>
                  <h2>Date and notes</h2>
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
                Notes
                <textarea
                  value={caseDraft.notes}
                  onChange={(event) => setCaseDraft({ ...caseDraft, notes: event.target.value })}
                  rows={4}
                />
              </label>
              <button type="submit" disabled={isUpdatingCase}>
                {isUpdatingCase ? 'Saving...' : 'Save changes'}
              </button>
            </form>
          )}

          <section className="card stack action-card">
            <div>
              <p className="eyebrow">Next actions</p>
              <h2>Prepare and review</h2>
            </div>
            <div className="guided-action-grid">
              <article>
                <strong>1. Prepare scan</strong>
                <p className="muted small-note">
                  Isolates the brain and prepares the tissue data needed for measurements.
                </p>
                <button
                  type="button"
                  onClick={handleStartPreprocessing}
                  disabled={!mriCase.capabilities.can_start_preprocessing || isStartingPreprocessing}
                  title={!mriCase.capabilities.can_start_preprocessing ? disabledHint(mriCase, 'prepare') : undefined}
                >
                  {isStartingPreprocessing ? 'Starting...' : 'Prepare scan'}
                </button>
              </article>
              <article>
                <strong>2. Create results</strong>
                <p className="muted small-note">
                  Builds the 3D tissue model and calculates volume and surface measurements.
                </p>
                <button
                  type="button"
                  onClick={handleStartMeshAnalysis}
                  disabled={!mriCase.capabilities.can_start_mesh_analysis || isStartingMesh}
                  title={!mriCase.capabilities.can_start_mesh_analysis ? disabledHint(mriCase, 'model') : undefined}
                >
                  {isStartingMesh ? 'Starting...' : 'Create 3D model'}
                </button>
              </article>
              <article>
                <strong>3. Review</strong>
                <p className="muted small-note">
                  Open the finished model, measurements, or compare dates for this subject.
                </p>
                <div className="button-row">
                  <button type="button" onClick={onOpenViewer} disabled={!mriCase.capabilities.can_view_meshes}>
                    3D view
                  </button>
                  <button type="button" className="secondary" onClick={onOpenStatistics} disabled={!mriCase.capabilities.can_view_metrics}>
                    Measurements
                  </button>
                  <button type="button" className="secondary" onClick={onOpenTimeComparison} disabled={!mriCase.capabilities.can_view_metrics}>
                    Compare dates
                  </button>
                </div>
              </article>
            </div>
          </section>
        </>
      )}

      {activeJob && (
        <JobStatusCard
          initialJob={activeJob}
          onJobChanged={handleJobUpdated}
          onFinished={handleJobFinished}
        />
      )}

      <section className="card stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Downloads</p>
            <h2>Result files</h2>
          </div>
          <button type="button" className="secondary" onClick={refreshArtifacts}>
            Refresh files
          </button>
        </div>
        <ArtifactList artifacts={artifacts?.artifacts ?? []} />
      </section>
    </main>
  )
}
