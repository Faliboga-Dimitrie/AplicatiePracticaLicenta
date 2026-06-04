import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { deleteCase, updateCase } from '../api/casesApi'
import { listSubjectCases } from '../api/subjectsApi'
import { CaseProgress } from '../components/CaseProgress'
import { Modal } from '../components/Modal'
import { UploadCaseForm } from '../components/UploadCaseForm'
import type { MriCase } from '../types/api'
import { formatCaseName, formatDateLabel, getCaseStageLabel } from '../utils/userFacing'
import { todayIsoDate } from '../utils/dates'

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
}

function toCaseEditorState(mriCase: MriCase): CaseEditorState {
  return {
    id: mriCase.id,
    acquisitionDate: mriCase.acquisition_date,
    notes: mriCase.notes ?? '',
  }
}

export function SubjectCasesPage({ subjectId, onBack, onSelectCase, onOpenTimeComparison }: SubjectCasesPageProps) {
  const [cases, setCases] = useState<MriCase[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingCase, setEditingCase] = useState<CaseEditorState | null>(null)
  const [isUpdating, setIsUpdating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<MriCase | null>(null)
  const [deletingCaseId, setDeletingCaseId] = useState<number | null>(null)

  const readyCounts = useMemo(() => {
    return {
      uploaded: cases.filter((mriCase) => mriCase.capabilities.raw_uploaded).length,
      prepared: cases.filter((mriCase) => mriCase.capabilities.has_fast_pve_outputs).length,
      finished: cases.filter((mriCase) => mriCase.capabilities.has_metrics || mriCase.capabilities.can_view_metrics).length,
    }
  }, [cases])

  const sortedCases = useMemo(
    () => [...cases].sort((a, b) => b.acquisition_date.localeCompare(a.acquisition_date)),
    [cases],
  )

  const refreshCases = useCallback(async () => {
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
  }, [subjectId])

  useEffect(() => {
    refreshCases()
  }, [refreshCases])

  function handleCreatedCase(createdCase: MriCase) {
    setCases((currentCases) => [createdCase, ...currentCases])
  }

  async function handleUpdateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingCase) return

    if (editingCase.acquisitionDate > todayIsoDate()) {
      setError('The acquisition date cannot be in the future.')
      return
    }

    setIsUpdating(true)
    setError(null)
    try {
      const response = await updateCase(editingCase.id, {
        acquisition_date: editingCase.acquisitionDate,
        notes: editingCase.notes.trim() || null,
      })
      setCases((currentCases) => currentCases.map((item) => (item.id === response.case.id ? response.case : item)))
      setEditingCase(null)
    } catch (updateError) {
      setError(apiMessage(updateError))
    } finally {
      setIsUpdating(false)
    }
  }

  async function handleDeleteCase() {
    if (!deleteTarget) return

    setDeletingCaseId(deleteTarget.id)
    setError(null)
    try {
      await deleteCase(deleteTarget.id)
      if (editingCase?.id === deleteTarget.id) setEditingCase(null)
      setCases((currentCases) => currentCases.filter((item) => item.id !== deleteTarget.id))
      setDeleteTarget(null)
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
          <p className="eyebrow">Subject</p>
          <h1>{subjectId}</h1>
          <p className="muted">Upload scans, follow their progress, and open completed results for this subject.</p>
        </div>
        <div className="button-row">
          {onOpenTimeComparison && (
            <button type="button" onClick={onOpenTimeComparison} disabled={readyCounts.finished < 2}>
              Compare dates
            </button>
          )}
          <button type="button" className="secondary" onClick={refreshCases} disabled={isLoading}>
            Refresh
          </button>
        </div>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span>Total scans</span>
          <strong>{cases.length}</strong>
        </article>
        <article className="metric-card">
          <span>Uploaded</span>
          <strong>{readyCounts.uploaded}</strong>
        </article>
        <article className="metric-card">
          <span>Prepared</span>
          <strong>{readyCounts.prepared}</strong>
        </article>
        <article className="metric-card">
          <span>Ready results</span>
          <strong>{readyCounts.finished}</strong>
        </article>
      </section>

      <section className="two-column">
        <div className="stack">
          {error && <p className="error-text">{error}</p>}
          {isLoading && <p className="muted">Loading MRI scans...</p>}
          {!isLoading && cases.length === 0 && (
            <article className="card empty-state">
              <h2>No MRI scans yet</h2>
              <p className="muted">Upload the first acquisition from the form on the right.</p>
            </article>
          )}

          <div className="card-list">
            {sortedCases.map((mriCase) => (
              <article className="card case-card" key={mriCase.id}>
                <div className="row-between">
                  <div>
                    <h2>{formatCaseName(mriCase)}</h2>
                    <p className="muted">Saved under subject {mriCase.subject_id}</p>
                  </div>
                  <span className="badge">{getCaseStageLabel(mriCase)}</span>
                </div>

                <CaseProgress mriCase={mriCase} compact />

                {mriCase.notes && <p>{mriCase.notes}</p>}

                <div className="button-row">
                  <button type="button" onClick={() => onSelectCase(mriCase.id)}>
                    Open scan
                  </button>
                  <button type="button" className="secondary" onClick={() => setEditingCase(toCaseEditorState(mriCase))}>
                    Edit notes/date
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    onClick={() => setDeleteTarget(mriCase)}
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
        </aside>
      </section>

      {editingCase && (
        <Modal title={formatDateLabel(editingCase.acquisitionDate)} eyebrow="Edit scan" onClose={() => setEditingCase(null)} hideCloseButton>
          <form className="form-grid" onSubmit={handleUpdateCase}>
            <label>
              Acquisition date
              <input
                type="date"
                value={editingCase.acquisitionDate}
                max={todayIsoDate()}
                onChange={(event) => setEditingCase({ ...editingCase, acquisitionDate: event.target.value })}
                required
              />
            </label>

            <label>
              Notes
              <textarea
                value={editingCase.notes}
                onChange={(event) => setEditingCase({ ...editingCase, notes: event.target.value })}
                rows={4}
              />
            </label>

            <div className="button-row modal-form-actions">
              <button type="submit" disabled={isUpdating}>
                {isUpdating ? 'Saving...' : 'Save changes'}
              </button>
              <button type="button" className="secondary" onClick={() => setEditingCase(null)} disabled={isUpdating}>
                Cancel
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleteTarget && (
        <Modal
          title="Delete scan?"
          eyebrow="Confirm deletion"
          onClose={() => setDeleteTarget(null)} hideCloseButton
          footer={(
            <>
              <button type="button" className="danger-button" onClick={handleDeleteCase} disabled={deletingCaseId === deleteTarget.id}>
                {deletingCaseId === deleteTarget.id ? 'Deleting...' : 'Delete scan'}
              </button>
              <button type="button" className="secondary" onClick={() => setDeleteTarget(null)} disabled={deletingCaseId === deleteTarget.id}>
                Cancel
              </button>
            </>
          )}
        >
          <p>This will delete the selected MRI scan and its generated result files.</p>
          <dl className="details-list clean-details-list">
            <div><dt>Subject</dt><dd>{deleteTarget.subject_id}</dd></div>
            <div><dt>Acquisition date</dt><dd>{formatDateLabel(deleteTarget.acquisition_date)}</dd></div>
            <div><dt>Status</dt><dd>{getCaseStageLabel(deleteTarget)}</dd></div>
            <div><dt>Notes</dt><dd>{deleteTarget.notes || 'No notes added.'}</dd></div>
          </dl>
        </Modal>
      )}
    </main>
  )
}
