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
  const openedFromCase = Boolean(caseId && subjectId)
  const [subjects, setSubjects] = useState<AuthorizedSubject[]>([])
  const [subjectCases, setSubjectCases] = useState<MriCase[]>([])
  const [selectedSubjectId, setSelectedSubjectId] = useState(subjectId ?? '')
  const [selectedCaseId, setSelectedCaseId] = useState<number | ''>(caseId ?? '')
  const [activeCase, setActiveCase] = useState<MriCase | null>(null)
  const [activeItems, setActiveItems] = useState<BrainViewerItem[]>([])
  const [pendingCase, setPendingCase] = useState<MriCase | null>(null)
  const [pendingItems, setPendingItems] = useState<BrainViewerItem[]>([])
  const [isLoadingSubjects, setIsLoadingSubjects] = useState(true)
  const [isLoadingCases, setIsLoadingCases] = useState(false)
  const [isLoadingViewer, setIsLoadingViewer] = useState(false)
  const [isPreparingScene, setIsPreparingScene] = useState(false)
  const [subjectTouched, setSubjectTouched] = useState(Boolean(subjectId))
  const [caseTouched, setCaseTouched] = useState(Boolean(caseId))
  const [hasCaseFieldBeenShown, setHasCaseFieldBeenShown] = useState(Boolean(subjectId))
  const [error, setError] = useState<string | null>(null)
  const activeObjectUrlsRef = useRef<string[]>([])
  const pendingObjectUrlsRef = useRef<string[]>([])

  const revokeUrls = useCallback((urls: string[]) => {
    urls.forEach((url) => URL.revokeObjectURL(url))
  }, [])

  const clearPending = useCallback(() => {
    revokeUrls(pendingObjectUrlsRef.current)
    pendingObjectUrlsRef.current = []
    setPendingCase(null)
    setPendingItems([])
    setIsPreparingScene(false)
  }, [revokeUrls])

  const promotePendingScene = useCallback(() => {
    if (!pendingCase) return
    revokeUrls(activeObjectUrlsRef.current)
    activeObjectUrlsRef.current = pendingObjectUrlsRef.current
    pendingObjectUrlsRef.current = []
    setActiveCase(pendingCase)
    setActiveItems(pendingItems)
    setPendingCase(null)
    setPendingItems([])
    setIsPreparingScene(false)
  }, [pendingCase, pendingItems, revokeUrls])

  useEffect(() => {
    let cancelled = false
    async function loadSubjects() {
      setIsLoadingSubjects(true)
      setError(null)
      try {
        const loaded = await listSubjects()
        if (!cancelled) setSubjects(loaded)
      } catch (loadError) {
        if (!cancelled) setError(apiMessage(loadError))
      } finally {
        if (!cancelled) setIsLoadingSubjects(false)
      }
    }
    loadSubjects()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!selectedSubjectId) {
      setSubjectCases([])
      setSelectedCaseId('')
      return
    }
    let cancelled = false
    async function loadCases() {
      setIsLoadingCases(true)
      setError(null)
      try {
        const loaded = await listSubjectCases(selectedSubjectId)
        if (!cancelled) {
          setSubjectCases(loaded)
          setHasCaseFieldBeenShown(true)
        }
      } catch (loadError) {
        if (!cancelled) setError(apiMessage(loadError))
      } finally {
        if (!cancelled) setIsLoadingCases(false)
      }
    }
    loadCases()
    return () => { cancelled = true }
  }, [selectedSubjectId])

  const loadViewer = useCallback(async () => {
    if (selectedCaseId === '') return

    clearPending()
    setIsLoadingViewer(true)
    setError(null)
    const newUrls: string[] = []
    try {
      const [loadedCase, artifactBundle] = await Promise.all([
        getCase(Number(selectedCaseId)),
        listViewerArtifacts(Number(selectedCaseId)),
      ])

      const glbArtifacts = artifactBundle.artifacts.filter((artifact) => isGlbName(artifact.name, artifact.mime_type))
      const loadedItems: BrainViewerItem[] = []

      for (const artifact of glbArtifacts) {
        const objectUrl = await createArtifactObjectUrl(artifact)
        newUrls.push(objectUrl)
        const item = toViewerItem(artifact, objectUrl)
        if (item) loadedItems.push(item)
      }

      pendingObjectUrlsRef.current = newUrls
      setPendingCase(loadedCase)
      setPendingItems(loadedItems)
      setIsPreparingScene(loadedItems.length > 0)
      if (loadedItems.length === 0) {
        revokeUrls(activeObjectUrlsRef.current)
        activeObjectUrlsRef.current = []
        setActiveCase(loadedCase)
        setActiveItems([])
      }
    } catch (loadError) {
      revokeUrls(newUrls)
      setError(apiMessage(loadError))
    } finally {
      setIsLoadingViewer(false)
    }
  }, [clearPending, revokeUrls, selectedCaseId])

  useEffect(() => {
    loadViewer()
  }, [loadViewer])

  useEffect(() => {
    return () => {
      revokeUrls(activeObjectUrlsRef.current)
      revokeUrls(pendingObjectUrlsRef.current)
    }
  }, [revokeUrls])

  const meshReadyCases = subjectCases.filter((entry) => entry.capabilities?.can_view_meshes || entry.capabilities?.has_meshes)
  const showCaseField = Boolean(selectedSubjectId) && (hasCaseFieldBeenShown || !isLoadingCases)
  const hasVisibleViewer = Boolean(activeCase)
  const isChangingCase = hasVisibleViewer && (isLoadingViewer || isPreparingScene)
  const initialCaseStillLoading = openedFromCase && !hasVisibleViewer && (isLoadingViewer || isPreparingScene || isLoadingSubjects || isLoadingCases)
  const firstViewerLoadInProgress = !initialCaseStillLoading && !hasVisibleViewer && selectedCaseId !== ''

  function handleSubjectChange(nextSubjectId: string) {
    setSelectedSubjectId(nextSubjectId)
    setSelectedCaseId('')
    setSubjectTouched(true)
    setCaseTouched(false)
    if (nextSubjectId) setHasCaseFieldBeenShown(true)
  }

  function handleCaseChange(nextCaseId: string) {
    setSelectedCaseId(nextCaseId ? Number(nextCaseId) : '')
    setCaseTouched(Boolean(nextCaseId))
  }

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back</button>
          <p className="eyebrow">3D view</p>
          <h1>{activeCase ? `${activeCase.subject_id} · ${activeCase.acquisition_date}` : 'Choose a scan'}</h1>
          <p className="muted">Select a subject and a completed scan to open its 3D brain tissue model.</p>
        </div>
        <button type="button" className="secondary" onClick={loadViewer} disabled={isLoadingViewer || selectedCaseId === ''}>Refresh model</button>
      </section>

      {error && <p className="error-text">{error}</p>}

      {initialCaseStillLoading ? (
        <section className="card loading-card"><p className="muted">Loading 3D visualization...</p></section>
      ) : (
        <section className="card form-grid choose-scan-card">
          <h2>Choose scan</h2>
          <label className={subjectTouched ? 'touched-field' : undefined}>
            Subject
            {isLoadingSubjects && <span className="muted small-note">Loading subjects...</span>}
            <select value={selectedSubjectId} disabled={isLoadingSubjects} onChange={(event) => handleSubjectChange(event.target.value)}>
              <option value="">Choose subject</option>
              {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.id} · {subject.case_count} cases</option>)}
            </select>
          </label>

          {selectedSubjectId && isLoadingCases && <p className="muted small-note">Loading cases...</p>}

          {showCaseField && (
            <label className={caseTouched ? 'touched-field' : undefined}>
              Case
              <select value={selectedCaseId} disabled={!selectedSubjectId || isLoadingCases} onChange={(event) => handleCaseChange(event.target.value)}>
                <option value="">Choose completed scan</option>
                {meshReadyCases.map((entry) => <option key={entry.id} value={entry.id}>{entry.acquisition_date}</option>)}
              </select>
            </label>
          )}

          {showCaseField && !isLoadingCases && <p className="muted small-note">Only scans with a completed 3D model are shown here.</p>}
        </section>
      )}

      {isChangingCase && <section className="card loading-card"><p className="muted">Loading for new case...</p></section>}
      {firstViewerLoadInProgress && <section className="card loading-card"><p className="muted">Loading 3D visualization...</p></section>}

      {hasVisibleViewer && (
        <Suspense fallback={<section className="card"><p className="muted">Loading 3D view...</p></section>}>
          <Brain3DViewer
            items={activeItems}
            title="3D brain tissue viewer"
            subtitle={activeCase ? `Loaded ${activeItems.length} tissue layers.` : 'Choose a completed scan to load its 3D model.'}
            isLoading={false}
            error={error}
            onReload={selectedCaseId === '' ? undefined : loadViewer}
          />
        </Suspense>
      )}

      {pendingItems.length > 0 && (
        <div className="viewer-preload-hidden" aria-hidden="true">
          <Suspense fallback={null}>
            <Brain3DViewer
              items={pendingItems}
              title="3D brain tissue viewer"
              subtitle="Preparing preview."
              isLoading={false}
              error={null}
              onSceneReady={promotePendingScene}
            />
          </Suspense>
        </div>
      )}
    </main>
  )
}
