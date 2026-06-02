import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { apiMessage } from '../api/client'
import { createArtifactObjectUrl, listViewerArtifacts } from '../api/artifactsApi'
import { getCase } from '../api/casesApi'
import { listSubjectCases, listSubjects } from '../api/subjectsApi'
import { inferViewerModeFromName, inferViewerTissueFromName, isGlbName } from '../components/brainViewerUtils'
import type { BrainViewerItem } from '../components/brainViewerUtils'
import type { Artifact, AuthorizedSubject, MriCase } from '../types/api'

const Brain3DViewer = lazy(() => import('../components/Brain3DViewer').then((module) => ({ default: module.Brain3DViewer })))

type Case3DViewerPageProps = {
  caseId?: number
  subjectId?: string
  onBack: () => void
}

function toViewerItem(artifact: Artifact, objectUrl: string): BrainViewerItem | null {
  const mode = inferViewerModeFromName(artifact.kind) ?? inferViewerModeFromName(artifact.name)
  const tissue = inferViewerTissueFromName(artifact.name, artifact.metadata?.tissue)
  if (!mode || !tissue || !isGlbName(artifact.name, artifact.mime_type)) {
    return null
  }
  return {
    id: artifact.name,
    name: artifact.name,
    tissue,
    mode,
    objectUrl,
  }
}

export function Case3DViewerPage({ caseId, subjectId, onBack }: Case3DViewerPageProps) {
  const [subjects, setSubjects] = useState<AuthorizedSubject[]>([])
  const [subjectCases, setSubjectCases] = useState<MriCase[]>([])
  const [selectedSubjectId, setSelectedSubjectId] = useState(subjectId ?? '')
  const [selectedCaseId, setSelectedCaseId] = useState<number | ''>(caseId ?? '')
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [items, setItems] = useState<BrainViewerItem[]>([])
  const [isLoadingSelection, setIsLoadingSelection] = useState(true)
  const [isLoadingCases, setIsLoadingCases] = useState(false)
  const [isLoadingViewer, setIsLoadingViewer] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const objectUrlsRef = useRef<string[]>([])

  const clearObjectUrls = useCallback(() => {
    objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
    objectUrlsRef.current = []
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadSubjects() {
      setIsLoadingSelection(true)
      setError(null)
      try {
        const loaded = await listSubjects()
        if (!cancelled) setSubjects(loaded)
      } catch (loadError) {
        if (!cancelled) setError(apiMessage(loadError))
      } finally {
        if (!cancelled) setIsLoadingSelection(false)
      }
    }
    loadSubjects()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!selectedSubjectId) {
      setSubjectCases([])
      if (!caseId) setSelectedCaseId('')
      return
    }
    let cancelled = false
    async function loadCases() {
      setIsLoadingCases(true)
      setError(null)
      try {
        const loaded = await listSubjectCases(selectedSubjectId)
        if (!cancelled) setSubjectCases(loaded)
      } catch (loadError) {
        if (!cancelled) setError(apiMessage(loadError))
      } finally {
        if (!cancelled) setIsLoadingCases(false)
      }
    }
    loadCases()
    return () => { cancelled = true }
  }, [selectedSubjectId, caseId])

  const loadViewer = useCallback(async () => {
    if (selectedCaseId === '') {
      setItems([])
      setMriCase(null)
      clearObjectUrls()
      return
    }

    setIsLoadingViewer(true)
    setError(null)
    try {
      const [loadedCase, artifactBundle] = await Promise.all([
        getCase(Number(selectedCaseId)),
        listViewerArtifacts(Number(selectedCaseId)),
      ])

      const glbArtifacts = artifactBundle.artifacts.filter((artifact) => isGlbName(artifact.name, artifact.mime_type))
      const loadedItems: BrainViewerItem[] = []
      const newUrls: string[] = []

      for (const artifact of glbArtifacts) {
        const objectUrl = await createArtifactObjectUrl(artifact)
        newUrls.push(objectUrl)
        const item = toViewerItem(artifact, objectUrl)
        if (item) loadedItems.push(item)
      }

      clearObjectUrls()
      objectUrlsRef.current = newUrls
      setMriCase(loadedCase)
      setItems(loadedItems)
    } catch (loadError) {
      setItems([])
      clearObjectUrls()
      setError(apiMessage(loadError))
    } finally {
      setIsLoadingViewer(false)
    }
  }, [clearObjectUrls, selectedCaseId])

  useEffect(() => {
    loadViewer()
  }, [loadViewer])

  useEffect(() => {
    return () => clearObjectUrls()
  }, [clearObjectUrls])

  const meshReadyCases = subjectCases.filter((entry) => entry.capabilities?.can_view_meshes || entry.capabilities?.has_meshes)

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back</button>
          <p className="eyebrow">3D view</p>
          <h1>{mriCase ? `${mriCase.subject_id} · ${mriCase.acquisition_date}` : 'Choose a case'}</h1>
          <p className="muted">Select a subject and a completed scan to open its 3D brain tissue model.</p>
        </div>
        <button type="button" className="secondary" onClick={loadViewer} disabled={isLoadingViewer || selectedCaseId === ''}>Refresh model</button>
      </section>

      {error && <p className="error-text">{error}</p>}

      <section className="card form-grid">
        <h2>Choose scan</h2>
        <label>
          Subject
          <select value={selectedSubjectId} disabled={isLoadingSelection} onChange={(event) => { setSelectedSubjectId(event.target.value); setSelectedCaseId('') }}>
            <option value="">Choose subject</option>
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.id} · {subject.case_count} cases</option>)}
          </select>
        </label>
        <label>
          Case
          <select value={selectedCaseId} disabled={!selectedSubjectId || isLoadingCases} onChange={(event) => setSelectedCaseId(event.target.value ? Number(event.target.value) : '')}>
            <option value="">Choose completed scan</option>
            {meshReadyCases.map((entry) => <option key={entry.id} value={entry.id}>{entry.acquisition_date}</option>)}
          </select>
        </label>
        <p className="muted small-note">Only scans with a completed 3D model are shown here.</p>
      </section>

      <Suspense fallback={<section className="card"><p className="muted">Loading 3D view...</p></section>}>
        <Brain3DViewer
          items={items}
          title="3D brain tissue viewer"
          subtitle={mriCase ? `Loaded ${items.length} tissue layers.` : 'Choose a completed scan to load its 3D model.'}
          isLoading={isLoadingViewer}
          error={selectedCaseId === '' ? null : error}
          onReload={selectedCaseId === '' ? undefined : loadViewer}
        />
      </Suspense>
    </main>
  )
}
