import { useCallback, useEffect, useState } from 'react'
import { apiMessage } from '../api/client'
import { getCase } from '../api/casesApi'
import { listArtifacts } from '../api/artifactsApi'
import { startMeshAnalysisJob, startPreprocessingJob } from '../api/jobsApi'
import { ArtifactList } from '../components/ArtifactList'
import { JobStatusCard } from '../components/JobStatusCard'
import type { CaseArtifacts, Job, MriCase } from '../types/api'

type CaseDetailPageProps = {
  caseId: number
  onBack: () => void
}

function capabilityText(value: boolean | undefined): string {
  return value ? 'yes' : 'no'
}

export function CaseDetailPage({ caseId, onBack }: CaseDetailPageProps) {
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [artifacts, setArtifacts] = useState<CaseArtifacts | null>(null)
  const [activeJob, setActiveJob] = useState<Job | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isStartingPreprocessing, setIsStartingPreprocessing] = useState(false)
  const [isStartingMesh, setIsStartingMesh] = useState(false)
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

  async function handleJobFinished() {
    await refreshAll()
  }

  const capabilities = mriCase?.capabilities

  return (
    <main className="page stack">
      <button type="button" className="link-button" onClick={onBack}>← Back to cases</button>

      <div className="row-between">
        <div>
          <p className="eyebrow">Step 3</p>
          <h1>Case #{caseId}</h1>
        </div>
        <button type="button" className="secondary" onClick={refreshAll} disabled={isLoading}>
          Refresh
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Loading case...</p>}

      {mriCase && (
        <section className="grid-two">
          <article className="card stack">
            <h2>Case details</h2>
            <dl className="details-list">
              <div><dt>Subject</dt><dd>{mriCase.subject_id}</dd></div>
              <div><dt>Acquisition date</dt><dd>{mriCase.acquisition_date}</dd></div>
              <div><dt>Status</dt><dd>{mriCase.status || 'none'}</dd></div>
              <div><dt>Case key</dt><dd>{mriCase.case_key || 'none'}</dd></div>
              <div><dt>Notes</dt><dd>{mriCase.notes || 'none'}</dd></div>
            </dl>
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
