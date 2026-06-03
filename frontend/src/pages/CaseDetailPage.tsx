import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { deleteCase, getCase, updateCase } from '../api/casesApi'
import { listArtifacts } from '../api/artifactsApi'
import { startProcessingJob } from '../api/jobsApi'
import { ArtifactList } from '../components/ArtifactList'
import { CaseProgress } from '../components/CaseProgress'
import { JobStatusCard } from '../components/JobStatusCard'
import { Modal } from '../components/Modal'
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

function todayIsoDate(): string {
  const now = new Date()
  const localMidnightSafe = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return localMidnightSafe.toISOString().slice(0, 10)
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

function processingDisabledHint(mriCase: MriCase): string {
  if (mriCase.capabilities.is_busy) return 'Processing is already running for this scan.'
  if (!mriCase.capabilities.raw_uploaded) return 'Upload an MRI file before processing this scan.'
  if (mriCase.capabilities.can_view_meshes && mriCase.capabilities.can_view_metrics) return 'This scan already has a 3D model and measurements.'
  return 'This scan cannot be processed yet.'
}

export function CaseDetailPage({ caseId, onBack, onOpenViewer, onOpenStatistics, onOpenTimeComparison }: CaseDetailPageProps) {
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [caseDraft, setCaseDraft] = useState<CaseEditorState | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [artifacts, setArtifacts] = useState<CaseArtifacts | null>(null)
  const { getTrackedJobForCase, trackJob, clearCaseJob } = useJobActivity()
  const [isLoading, setIsLoading] = useState(true)
  const [isStartingProcessing, setIsStartingProcessing] = useState(false)
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

  async function handleStartProcessing() {
    setIsStartingProcessing(true)
    setError(null)
    try {
      const job = await startProcessingJob(caseId)
      trackJob(job)
      await refreshCase()
    } catch (startError) {
      setError(apiMessage(startError))
    } finally {
      setIsStartingProcessing(false)
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

    if (caseDraft.acquisitionDate > todayIsoDate()) {
      setError('The acquisition date cannot be in the future.')
      return
    }

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

    setIsDeletingCase(true)
    setError(null)
    try {
      await deleteCase(mriCase.id)
      setDeleteDialogOpen(false)
      onBack()
    } catch (deleteError) {
      setError(apiMessage(deleteError))
    } finally {
      setIsDeletingCase(false)
    }
  }

  if (isLoading) {
    return (
      <main className="page stack">
        <section className="card loading-card">
          <button type="button" className="link-button" onClick={onBack}>← Back to scans</button>
          <h1>Loading scan...</h1>
          <p className="muted">Opening the selected MRI scan.</p>
        </section>
      </main>
    )
  }

  if (!mriCase) {
    return (
      <main className="page stack">
        <section className="card empty-state">
          <button type="button" className="link-button" onClick={onBack}>← Back to scans</button>
          <h1>Scan not found</h1>
          {error && <p className="error-text">{error}</p>}
        </section>
      </main>
    )
  }

  const hasArtifacts = Boolean(artifacts?.artifacts.length)
  const canStartProcessing = Boolean(
    mriCase.capabilities.raw_uploaded
    && !mriCase.capabilities.is_busy
    && !(mriCase.capabilities.can_view_meshes && mriCase.capabilities.can_view_metrics),
  )

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to scans</button>
          <p className="eyebrow">MRI scan</p>
          <h1>{formatCaseName(mriCase)}</h1>
          <p className="muted">Follow the guided steps, then open the visual and measurement results.</p>
        </div>
        <button type="button" className="secondary" onClick={refreshAll}>
          Refresh
        </button>
      </section>

      {error && <p className="error-text">{error}</p>}

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
            <button type="button" className="danger-button" onClick={() => setDeleteDialogOpen(true)} disabled={isDeletingCase}>
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

      <section className="card stack action-card">
        <div>
          <p className="eyebrow">Next actions</p>
          <h2>Process and review</h2>
          <p className="muted">
            One action prepares the MRI scan, creates the 3D tissue model, and calculates the measurements.
          </p>
        </div>
        <div className="single-action-panel">
          <button
            type="button"
            onClick={handleStartProcessing}
            disabled={!canStartProcessing || isStartingProcessing}
            title={!canStartProcessing ? processingDisabledHint(mriCase) : undefined}
          >
            {isStartingProcessing ? 'Starting...' : 'Process MRI'}
          </button>
          <p className="muted small-note">The checklist above will update as the scan moves toward finished results.</p>
        </div>
        <div className="button-row">
          <button type="button" className="outline-action" onClick={onOpenViewer} disabled={!mriCase.capabilities.can_view_meshes}>
            3D view
          </button>
          <button type="button" className="outline-action" onClick={onOpenStatistics} disabled={!mriCase.capabilities.can_view_metrics}>
            Measurements
          </button>
          <button type="button" className="outline-action" onClick={onOpenTimeComparison} disabled={!mriCase.capabilities.can_view_metrics}>
            Compare dates
          </button>
        </div>
      </section>

      {activeJob && (
        <JobStatusCard
          initialJob={activeJob}
          onJobChanged={handleJobUpdated}
          onFinished={handleJobFinished}
        />
      )}

      <section className={`card stack ${hasArtifacts ? '' : 'disabled-card'}`}>
        <div className="row-between">
          <div>
            <p className="eyebrow">Downloads</p>
            <h2>Result files</h2>
          </div>
          <button type="button" className="secondary" onClick={refreshArtifacts} disabled={!hasArtifacts}>
            Refresh files
          </button>
        </div>
        <ArtifactList artifacts={artifacts?.artifacts ?? []} />
      </section>

      {caseDraft && (
        <Modal title="Date and notes" eyebrow="Edit scan" onClose={() => setCaseDraft(null)} hideCloseButton>
          <form className="form-grid" onSubmit={handleUpdateCase}>
            <label>
              Acquisition date
              <input
                type="date"
                value={caseDraft.acquisitionDate}
                max={todayIsoDate()}
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
            <div className="button-row modal-form-actions">
              <button type="submit" disabled={isUpdatingCase}>
                {isUpdatingCase ? 'Saving...' : 'Save changes'}
              </button>
              <button type="button" className="secondary" onClick={() => setCaseDraft(null)} disabled={isUpdatingCase}>
                Cancel
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleteDialogOpen && (
        <Modal
          title="Delete scan?"
          eyebrow="Confirm deletion"
          onClose={() => setDeleteDialogOpen(false)}
          footer={(
            <>
              <button type="button" className="danger-button" onClick={handleDeleteCase} disabled={isDeletingCase}>
                {isDeletingCase ? 'Deleting...' : 'Delete scan'}
              </button>
              <button type="button" className="secondary" onClick={() => setDeleteDialogOpen(false)} disabled={isDeletingCase}>
                Cancel
              </button>
            </>
          )}
        >
          <p>This will delete the selected MRI scan and its generated result files.</p>
          <dl className="details-list clean-details-list">
            <div><dt>Subject</dt><dd>{mriCase.subject_id}</dd></div>
            <div><dt>Acquisition date</dt><dd>{formatDateLabel(mriCase.acquisition_date)}</dd></div>
            <div><dt>Status</dt><dd>{getCaseStageLabel(mriCase)}</dd></div>
            <div><dt>Notes</dt><dd>{mriCase.notes || 'No notes added.'}</dd></div>
          </dl>
        </Modal>
      )}
    </main>
  )
}
