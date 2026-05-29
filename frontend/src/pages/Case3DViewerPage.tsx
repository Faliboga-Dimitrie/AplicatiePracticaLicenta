import { useCallback, useEffect, useRef, useState } from 'react'
import { apiMessage } from '../api/client'
import { createArtifactObjectUrl, listViewerArtifacts } from '../api/artifactsApi'
import { getCase } from '../api/casesApi'
import { Brain3DViewer, inferViewerModeFromName, inferViewerTissueFromName, isGlbName } from '../components/Brain3DViewer'
import type { BrainViewerItem } from '../components/Brain3DViewer'
import type { Artifact, MriCase } from '../types/api'

type Case3DViewerPageProps = {
  caseId: number
  onBack: () => void
}

function toViewerItem(artifact: Artifact, objectUrl: string): BrainViewerItem | null {
  const mode = inferViewerModeFromName(artifact.kind) ?? inferViewerModeFromName(artifact.name)
  const tissue = inferViewerTissueFromName(artifact.name, artifact.metadata?.tissue)

  if (!mode || !tissue || !isGlbName(artifact.name, artifact.mime_type)) {
    return null
  }

  return {
    id: `${mode}-${tissue}-${artifact.name}`,
    name: artifact.name,
    tissue,
    mode,
    objectUrl,
  }
}

export function Case3DViewerPage({ caseId, onBack }: Case3DViewerPageProps) {
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [items, setItems] = useState<BrainViewerItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const objectUrlsRef = useRef<string[]>([])

  const revokeCurrentObjectUrls = useCallback(() => {
    objectUrlsRef.current.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    objectUrlsRef.current = []
  }, [])

  const loadViewer = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    const createdItems: BrainViewerItem[] = []
    const createdUrls: string[] = []

    try {
      const [loadedCase, artifactBundle] = await Promise.all([getCase(caseId), listViewerArtifacts(caseId)])
      setMriCase(loadedCase)

      const glbArtifacts = artifactBundle.artifacts.filter((artifact) => {
        const mode = inferViewerModeFromName(artifact.kind) ?? inferViewerModeFromName(artifact.name)
        const tissue = inferViewerTissueFromName(artifact.name, artifact.metadata?.tissue)
        return Boolean(mode && tissue && isGlbName(artifact.name, artifact.mime_type))
      })

      for (const artifact of glbArtifacts) {
        const objectUrl = await createArtifactObjectUrl(artifact)
        const viewerItem = toViewerItem(artifact, objectUrl)

        if (!viewerItem) {
          URL.revokeObjectURL(objectUrl)
          continue
        }

        createdItems.push(viewerItem)
        createdUrls.push(objectUrl)
      }

      revokeCurrentObjectUrls()
      objectUrlsRef.current = createdUrls
      setItems(createdItems)
    } catch (loadError) {
      createdUrls.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
      setError(apiMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [caseId, revokeCurrentObjectUrls])

  useEffect(() => {
    loadViewer()
    return () => {
      revokeCurrentObjectUrls()
    }
  }, [loadViewer, revokeCurrentObjectUrls])

  return (
    <main className="page viewer-page stack">
      <section className="page-header-card viewer-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to case</button>
          <p className="eyebrow">Interactive 3D viewer</p>
          <h1>{mriCase ? `${mriCase.subject_id} · ${mriCase.acquisition_date}` : `Case #${caseId}`}</h1>
          <p className="muted">Inspect GLB mesh and wireframe artifacts using browser-side WebGL controls.</p>
        </div>
      </section>

      <Brain3DViewer
        items={items}
        title="Runtime GLB controls"
        subtitle="These options change the WebGL scene only. They do not re-export or modify the stored GLB files."
        isLoading={isLoading}
        error={error}
        onReload={loadViewer}
      />
    </main>
  )
}
