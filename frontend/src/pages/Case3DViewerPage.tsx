import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Center, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { apiMessage } from '../api/client'
import { createArtifactObjectUrl } from '../api/artifactsApi'
import { getCase } from '../api/casesApi'
import { listArtifacts } from '../api/artifactsApi'
import type { Artifact, MriCase } from '../types/api'

type Case3DViewerPageProps = {
  caseId: number
  onBack: () => void
}

type Tissue = 'gm' | 'wm' | 'csf' | 'unknown'
type ArtifactMode = 'mesh' | 'wireframe'

type ViewerArtifact = {
  id: string
  artifact: Artifact
  tissue: Tissue
  mode: ArtifactMode
  objectUrl: string
}

type TissueControls = Record<Tissue, {
  visible: boolean
  opacity: number
}>

type ViewerTransform = {
  scale: number
  rotateX: number
  rotateY: number
  rotateZ: number
}

const tissueLabels: Record<Tissue, string> = {
  gm: 'Gray matter',
  wm: 'White matter',
  csf: 'CSF',
  unknown: 'Other',
}

const tissueColors: Record<Tissue, string> = {
  gm: '#f97316',
  wm: '#e2e8f0',
  csf: '#38bdf8',
  unknown: '#a78bfa',
}

const defaultTissueControls: TissueControls = {
  gm: { visible: true, opacity: 0.58 },
  wm: { visible: true, opacity: 0.46 },
  csf: { visible: true, opacity: 0.36 },
  unknown: { visible: true, opacity: 0.55 },
}

function normalizeKind(kind: string): ArtifactMode | null {
  const normalized = kind.toLowerCase()
  if (normalized.includes('wireframe')) {
    return 'wireframe'
  }
  if (normalized.includes('mesh')) {
    return 'mesh'
  }
  return null
}

function inferTissue(artifact: Artifact): Tissue {
  const metadataTissue = artifact.metadata?.tissue
  if (metadataTissue === 'gm' || metadataTissue === 'wm' || metadataTissue === 'csf') {
    return metadataTissue
  }

  const name = artifact.name.toLowerCase()
  if (name.includes('gray') || name.includes('_gm') || name.includes('gm_') || name.includes('-gm')) {
    return 'gm'
  }
  if (name.includes('white') || name.includes('_wm') || name.includes('wm_') || name.includes('-wm')) {
    return 'wm'
  }
  if (name.includes('csf') || name.includes('cerebrospinal')) {
    return 'csf'
  }
  return 'unknown'
}

function isGlbArtifact(artifact: Artifact): boolean {
  return artifact.name.toLowerCase().endsWith('.glb') || artifact.mime_type === 'model/gltf-binary'
}

function ModelLayer({
  item,
  controls,
  transform,
  showMeshes,
  showWireframes,
  doubleSided,
}: {
  item: ViewerArtifact
  controls: TissueControls
  transform: ViewerTransform
  showMeshes: boolean
  showWireframes: boolean
  doubleSided: boolean
}) {
  const gltf = useGLTF(item.objectUrl)
  const control = controls[item.tissue] ?? controls.unknown
  const shouldShow = control.visible && (item.mode === 'mesh' ? showMeshes : showWireframes)

  const scene = useMemo(() => {
    const clone = gltf.scene.clone(true)
    clone.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) {
        return
      }

      const sourceMaterial = object.material
      const materials = Array.isArray(sourceMaterial) ? sourceMaterial : [sourceMaterial]
      const clonedMaterials = materials.map((material) => {
        const cloned = material.clone()
        cloned.transparent = control.opacity < 1 || item.mode === 'wireframe'
        cloned.opacity = item.mode === 'wireframe' ? Math.min(1, Math.max(0.25, control.opacity + 0.25)) : control.opacity
        cloned.depthWrite = cloned.opacity >= 0.95
        cloned.side = doubleSided ? THREE.DoubleSide : THREE.FrontSide
        const materialWithColor = cloned as THREE.Material & { color?: THREE.Color }
        if (materialWithColor.color instanceof THREE.Color) {
          materialWithColor.color.set(tissueColors[item.tissue])
        }
        const materialWithWireframe = cloned as THREE.Material & { wireframe?: boolean }
        if (typeof materialWithWireframe.wireframe === 'boolean') {
          materialWithWireframe.wireframe = item.mode === 'wireframe'
        }
        return cloned
      })

      object.material = Array.isArray(sourceMaterial) ? clonedMaterials : clonedMaterials[0]
    })
    return clone
  }, [control.opacity, doubleSided, gltf.scene, item.mode, item.tissue])

  useEffect(() => {
    return () => {
      scene.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) {
          return
        }
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach((material) => material.dispose())
      })
    }
  }, [scene])

  return (
    <primitive
      object={scene}
      visible={shouldShow}
      scale={transform.scale}
      rotation={[transform.rotateX, transform.rotateY, transform.rotateZ]}
    />
  )
}

function AutoRotateGroup({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((_, delta) => {
    if (enabled && groupRef.current) {
      groupRef.current.rotation.y += delta * 0.28
    }
  })

  return <group ref={groupRef}>{children}</group>
}

function BrainGlbViewer({
  items,
  controls,
  transform,
  showMeshes,
  showWireframes,
  doubleSided,
  autoRotate,
}: {
  items: ViewerArtifact[]
  controls: TissueControls
  transform: ViewerTransform
  showMeshes: boolean
  showWireframes: boolean
  doubleSided: boolean
  autoRotate: boolean
}) {
  return (
    <Canvas camera={{ position: [0, -260, 130], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={['#08111f']} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[80, -120, 160]} intensity={2.1} />
      <directionalLight position={[-120, 80, -80]} intensity={0.9} />
      <gridHelper args={[260, 16, '#1d4ed8', '#1f2937']} position={[0, 0, -70]} />
      <axesHelper args={[60]} />
      <Suspense fallback={null}>
        <Center>
          <AutoRotateGroup enabled={autoRotate}>
            {items.map((item) => (
              <ModelLayer
              key={item.id}
              item={item}
              controls={controls}
              transform={transform}
              showMeshes={showMeshes}
              showWireframes={showWireframes}
              doubleSided={doubleSided}
            />
            ))}
          </AutoRotateGroup>
        </Center>
      </Suspense>
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
    </Canvas>
  )
}

function formatRadians(value: number): string {
  return `${Math.round((value * 180) / Math.PI)}°`
}

export function Case3DViewerPage({ caseId, onBack }: Case3DViewerPageProps) {
  const [mriCase, setMriCase] = useState<MriCase | null>(null)
  const [items, setItems] = useState<ViewerArtifact[]>([])
  const [controls, setControls] = useState<TissueControls>(defaultTissueControls)
  const [showMeshes, setShowMeshes] = useState(true)
  const [showWireframes, setShowWireframes] = useState(true)
  const [doubleSided, setDoubleSided] = useState(true)
  const [autoRotate, setAutoRotate] = useState(false)
  const [transform, setTransform] = useState<ViewerTransform>({ scale: 1, rotateX: 0, rotateY: 0, rotateZ: 0 })
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
    const createdUrls: ViewerArtifact[] = []

    try {
      const [loadedCase, artifactBundle] = await Promise.all([getCase(caseId), listArtifacts(caseId)])
      setMriCase(loadedCase)

      const viewerArtifacts = artifactBundle.artifacts
        .map((artifact) => ({ artifact, mode: normalizeKind(artifact.kind) }))
        .filter((entry): entry is { artifact: Artifact; mode: ArtifactMode } => Boolean(entry.mode) && isGlbArtifact(entry.artifact))

      for (const entry of viewerArtifacts) {
        const objectUrl = await createArtifactObjectUrl(entry.artifact)
        createdUrls.push({
          id: `${entry.mode}-${entry.artifact.name}`,
          artifact: entry.artifact,
          tissue: inferTissue(entry.artifact),
          mode: entry.mode,
          objectUrl,
        })
      }

      revokeCurrentObjectUrls()
      objectUrlsRef.current = createdUrls.map((item) => item.objectUrl)
      setItems(createdUrls)
    } catch (loadError) {
      createdUrls.forEach((item) => URL.revokeObjectURL(item.objectUrl))
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

  function updateTissue(tissue: Tissue, patch: Partial<TissueControls[Tissue]>) {
    setControls((current) => ({
      ...current,
      [tissue]: {
        ...current[tissue],
        ...patch,
      },
    }))
  }

  const visibleCount = items.filter((item) => {
    const tissueControl = controls[item.tissue] ?? controls.unknown
    return tissueControl.visible && (item.mode === 'mesh' ? showMeshes : showWireframes)
  }).length

  const hasMeshes = items.some((item) => item.mode === 'mesh')
  const hasWireframes = items.some((item) => item.mode === 'wireframe')

  return (
    <main className="page viewer-page stack">
      <section className="page-header-card viewer-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to case</button>
          <p className="eyebrow">Interactive 3D viewer</p>
          <h1>{mriCase ? `${mriCase.subject_id} · ${mriCase.acquisition_date}` : `Case #${caseId}`}</h1>
          <p className="muted">Inspect GLB mesh and wireframe artifacts using browser-side WebGL controls.</p>
        </div>
        <div className="button-row">
          <button type="button" className="secondary" onClick={loadViewer} disabled={isLoading}>Reload GLBs</button>
          <button type="button" className="secondary" onClick={() => setTransform({ scale: 1, rotateX: 0, rotateY: 0, rotateZ: 0 })}>Reset transform</button>
        </div>
      </section>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Loading protected GLB artifacts...</p>}

      <section className="viewer-layout">
        <aside className="card stack viewer-controls-panel">
          <div>
            <p className="eyebrow">Scene controls</p>
            <h2>Runtime GLB controls</h2>
            <p className="muted small-note">These options change the WebGL scene only. They do not re-export or modify the stored GLB files.</p>
          </div>

          <div className="viewer-toggle-grid">
            <label className="checkbox-row">
              <input type="checkbox" checked={showMeshes} disabled={!hasMeshes} onChange={(event) => setShowMeshes(event.target.checked)} />
              Meshes
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={showWireframes} disabled={!hasWireframes} onChange={(event) => setShowWireframes(event.target.checked)} />
              Wireframes
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={doubleSided} onChange={(event) => setDoubleSided(event.target.checked)} />
              Double-sided material
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={autoRotate} onChange={(event) => setAutoRotate(event.target.checked)} />
              Auto rotate
            </label>
          </div>

          <div className="stack compact-stack">
            <h3>Tissues</h3>
            {(['gm', 'wm', 'csf', 'unknown'] as Tissue[]).map((tissue) => (
              <div className="tissue-control" key={tissue}>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={controls[tissue].visible}
                    onChange={(event) => updateTissue(tissue, { visible: event.target.checked })}
                  />
                  <span className="tissue-dot" style={{ background: tissueColors[tissue] }} />
                  {tissueLabels[tissue]}
                </label>
                <label className="range-label">
                  Opacity {Math.round(controls[tissue].opacity * 100)}%
                  <input
                    type="range"
                    min="0.05"
                    max="1"
                    step="0.05"
                    value={controls[tissue].opacity}
                    onChange={(event) => updateTissue(tissue, { opacity: Number(event.target.value) })}
                  />
                </label>
              </div>
            ))}
          </div>

          <div className="stack compact-stack">
            <h3>Model transform</h3>
            <label className="range-label">
              Scale {transform.scale.toFixed(2)}×
              <input
                type="range"
                min="0.1"
                max="3"
                step="0.05"
                value={transform.scale}
                onChange={(event) => setTransform({ ...transform, scale: Number(event.target.value) })}
              />
            </label>
            <label className="range-label">
              Rotate X {formatRadians(transform.rotateX)}
              <input
                type="range"
                min={-Math.PI}
                max={Math.PI}
                step="0.05"
                value={transform.rotateX}
                onChange={(event) => setTransform({ ...transform, rotateX: Number(event.target.value) })}
              />
            </label>
            <label className="range-label">
              Rotate Y {formatRadians(transform.rotateY)}
              <input
                type="range"
                min={-Math.PI}
                max={Math.PI}
                step="0.05"
                value={transform.rotateY}
                onChange={(event) => setTransform({ ...transform, rotateY: Number(event.target.value) })}
              />
            </label>
            <label className="range-label">
              Rotate Z {formatRadians(transform.rotateZ)}
              <input
                type="range"
                min={-Math.PI}
                max={Math.PI}
                step="0.05"
                value={transform.rotateZ}
                onChange={(event) => setTransform({ ...transform, rotateZ: Number(event.target.value) })}
              />
            </label>
          </div>

          <div className="viewer-help-card">
            <strong>Orbit controls</strong>
            <p>Drag to rotate, scroll to zoom, right-drag to pan. Inside/fly camera will come in the next iteration.</p>
          </div>
        </aside>

        <section className="card viewer-canvas-card">
          <div className="viewer-canvas-toolbar">
            <span className="badge">{visibleCount}/{items.length} layers visible</span>
            <span className="muted small-note">GLB files are fetched with your bearer token, then loaded as local object URLs.</span>
          </div>
          <div className="viewer-canvas-wrap">
            {items.length > 0 ? (
              <BrainGlbViewer
                items={items}
                controls={controls}
                transform={transform}
                showMeshes={showMeshes}
                showWireframes={showWireframes}
                doubleSided={doubleSided}
                autoRotate={autoRotate}
              />
            ) : (
              <div className="viewer-empty-state">
                <h2>No GLB artifacts found</h2>
                <p className="muted">Run mesh analysis first, then return to this viewer.</p>
              </div>
            )}
          </div>
        </section>
      </section>
    </main>
  )
}
