import { useEffect, useState } from 'react'
import { apiMessage } from '../api/client'
import { listSubjectCases } from '../api/subjectsApi'
import { UploadCaseForm } from '../components/UploadCaseForm'
import type { MriCase } from '../types/api'

type SubjectCasesPageProps = {
  subjectId: string
  onBack: () => void
  onSelectCase: (caseId: number) => void
}

export function SubjectCasesPage({ subjectId, onBack, onSelectCase }: SubjectCasesPageProps) {
  const [cases, setCases] = useState<MriCase[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <main className="page two-column">
      <section className="stack">
        <button type="button" className="link-button" onClick={onBack}>← Back to subjects</button>
        <div className="row-between">
          <div>
            <p className="eyebrow">Step 2</p>
            <h1>{subjectId}</h1>
          </div>
          <button type="button" className="secondary" onClick={refreshCases} disabled={isLoading}>
            Refresh
          </button>
        </div>

        {error && <p className="error-text">{error}</p>}
        {isLoading && <p className="muted">Loading cases...</p>}
        {!isLoading && cases.length === 0 && <p className="muted">No MRI cases for this subject yet.</p>}

        <div className="card-list">
          {cases.map((mriCase) => (
            <button
              type="button"
              className="card clickable-card"
              key={mriCase.id}
              onClick={() => onSelectCase(mriCase.id)}
            >
              <div className="row-between">
                <strong>Case #{mriCase.id}</strong>
                <span className="badge">{mriCase.status || 'no status'}</span>
              </div>
              <p className="muted">Acquisition date: {mriCase.acquisition_date}</p>
              <p className="muted">Raw uploaded: {mriCase.capabilities.raw_uploaded ? 'yes' : 'no'}</p>
              {mriCase.notes && <p>{mriCase.notes}</p>}
            </button>
          ))}
        </div>
      </section>

      <aside>
        <UploadCaseForm subjectId={subjectId} onCreated={handleCreatedCase} />
      </aside>
    </main>
  )
}
