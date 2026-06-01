import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { deleteCase, updateCase } from '../api/casesApi'
import { listSubjectCases } from '../api/subjectsApi'
import { UploadCaseForm } from '../components/UploadCaseForm'
import type { MriCase } from '../types/api'

type SubjectCasesPageProps = {
  subjectId: string
  onBack: () => void
  onSelectCase: (caseId: number) => void
  onOpenTimeComparison?: () => void
}

type CaseEditorState = {
  id: number
  acquisitionDate: string
  notes: string
  status: string
}

function toCaseEditorState(mriCase: MriCase): CaseEditorState {
  return {
    id: mriCase.id,
    acquisitionDate: mriCase.acquisition_date,
    notes: mriCase.notes ?? '',
    status: mriCase.status ?? '',
  }
}

function readinessLabel(mriCase: MriCase): string {
  if (mriCase.capabilities.has_meshes) {
    return 'meshes ready'
  }
  if (mriCase.capabilities.has_fast_pve_outputs) {
    return 'segmentation ready'
  }
  if (mriCase.capabilities.raw_uploaded) {
    return 'raw uploaded'
  }
  return 'missing raw file'
}

export function SubjectCasesPage({ subjectId, onBack, onSelectCase, onOpenTimeComparison }: SubjectCasesPageProps) {
  const [cases, setCases] = useState<MriCase[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingCase, setEditingCase] = useState<CaseEditorState | null>(null)
  const [isUpdating, setIsUpdating] = useState(false)
  const [deletingCaseId, setDeletingCaseId] = useState<number | null>(null)

  const readyCounts = useMemo(() => {
    return {
      raw: cases.filter((mriCase) => mriCase.capabilities.raw_uploaded).length,
      fast: cases.filter((mriCase) => mriCase.capabilities.has_fast_pve_outputs).length,
      mesh: cases.filter((mriCase) => mriCase.capabilities.has_meshes).length,
    }
  }, [cases])

  async function refreshCases() {
    setIsLoading(true)
    setError(null)
    try {
      const loadedCases = await listSubjectCases(subjectId)
      setCases(loadedCases)
    } catch (loadError) {
      setError(apiMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshCases()
  }, [subjectId])

  function handleCreatedCase(createdCase: MriCase) {
    setCases((currentCases) => [createdCase, ...currentCases])
  }

  async function handleUpdateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingCase) {
      return
    }

    setIsUpdating(true)
    setError(null)
    try {
      const response = await updateCase(editingCase.id, {
        acquisition_date: editingCase.acquisitionDate,
        notes: editingCase.notes.trim() || null,
        status: editingCase.status.trim() || null,
      })
      setCases((currentCases) => currentCases.map((item) => (item.id === response.case.id ? response.case : item)))
      setEditingCase(null)
    } catch (updateError) {
      setError(apiMessage(updateError))
    } finally {
      setIsUpdating(false)
    }
  }

  async function handleDeleteCase(mriCase: MriCase) {
    const confirmed = window.confirm(
      `Delete case #${mriCase.id} from ${mriCase.acquisition_date}? This also deletes its local workspace files.`,
    )
    if (!confirmed) {
      return
    }

    setDeletingCaseId(mriCase.id)
    setError(null)
    try {
      await deleteCase(mriCase.id)
      if (editingCase?.id === mriCase.id) {
        setEditingCase(null)
      }
      setCases((currentCases) => currentCases.filter((item) => item.id !== mriCase.id))
    } catch (deleteError) {
      setError(apiMessage(deleteError))
    } finally {
      setDeletingCaseId(null)
    }
  }

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to subjects</button>
          <p className="eyebrow">Subject workspace</p>
          <h1>{subjectId}</h1>
          <p className="muted">Manage dated acquisitions, raw uploads and processing readiness for this subject.</p>
        </div>
        <div className="button-row">
          {onOpenTimeComparison && (
            <button
              type="button"
              onClick={onOpenTimeComparison}
              disabled={readyCounts.mesh < 2}
            >
              Compare over time
            </button>
          )}
          <button type="button" className="secondary" onClick={refreshCases} disabled={isLoading}>
            Refresh
          </button>
        </div>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span>Total cases</span>
          <strong>{cases.length}</strong>
        </article>
        <article className="metric-card">
          <span>Raw uploaded</span>
          <strong>{readyCounts.raw}</strong>
        </article>
        <article className="metric-card">
          <span>FAST ready</span>
          <strong>{readyCounts.fast}</strong>
        </article>
        <article className="metric-card">
          <span>Mesh ready</span>
          <strong>{readyCounts.mesh}</strong>
        </article>
      </section>

      <section className="two-column">
        <div className="stack">
          {error && <p className="error-text">{error}</p>}
          {isLoading && <p className="muted">Loading cases...</p>}
          {!isLoading && cases.length === 0 && (
            <article className="card empty-state">
              <h2>No MRI cases yet</h2>
              <p className="muted">Upload the first raw NIfTI acquisition from the form on the right.</p>
            </article>
          )}

          <div className="card-list">
            {cases.map((mriCase) => (
              <article className="card case-card" key={mriCase.id}>
                <div className="row-between">
                  <div>
                    <h2>Case #{mriCase.id}</h2>
                    <p className="muted">Acquisition date: {mriCase.acquisition_date}</p>
                  </div>
                  <span className="badge">{mriCase.status || 'no status'}</span>
                </div>

                <div className="readiness-row">
                  <span className="status-pill">{readinessLabel(mriCase)}</span>
                  <span>Raw: {mriCase.capabilities.raw_uploaded ? 'yes' : 'no'}</span>
                  <span>FAST: {mriCase.capabilities.has_fast_pve_outputs ? 'yes' : 'no'}</span>
                  <span>Mesh: {mriCase.capabilities.has_meshes ? 'yes' : 'no'}</span>
                </div>

                {mriCase.notes && <p>{mriCase.notes}</p>}

                <div className="button-row">
                  <button type="button" onClick={() => onSelectCase(mriCase.id)}>
                    Open processing
                  </button>
                  <button type="button" className="secondary" onClick={() => setEditingCase(toCaseEditorState(mriCase))}>
                    Edit case
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    onClick={() => handleDeleteCase(mriCase)}
                    disabled={deletingCaseId === mriCase.id}
                  >
                    {deletingCaseId === mriCase.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>

        <aside className="stack">
          <UploadCaseForm subjectId={subjectId} onCreated={handleCreatedCase} />

          {editingCase && (
            <form className="card form-grid" onSubmit={handleUpdateCase}>
              <div className="row-between">
                <div>
                  <p className="eyebrow">Edit case</p>
                  <h2>Case #{editingCase.id}</h2>
                </div>
                <button type="button" className="secondary" onClick={() => setEditingCase(null)}>
                  Cancel
                </button>
              </div>

              <label>
                Acquisition date
                <input
                  type="date"
                  value={editingCase.acquisitionDate}
                  onChange={(event) => setEditingCase({ ...editingCase, acquisitionDate: event.target.value })}
                  required
                />
              </label>

              <label>
                Status
                <select
                  value={editingCase.status}
                  onChange={(event) => setEditingCase({ ...editingCase, status: event.target.value })}
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

              <p className="muted small-note">
                Status is usually managed by background jobs. Edit it only for correction/testing.
              </p>

              <label>
                Notes
                <textarea
                  value={editingCase.notes}
                  onChange={(event) => setEditingCase({ ...editingCase, notes: event.target.value })}
                  rows={4}
                />
              </label>

              <button type="submit" disabled={isUpdating}>
                {isUpdating ? 'Saving...' : 'Save case changes'}
              </button>
            </form>
          )}
        </aside>
      </section>
    </main>
  )
}
