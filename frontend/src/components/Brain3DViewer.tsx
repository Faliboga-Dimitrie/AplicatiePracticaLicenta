import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Center, Html, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

export type ViewerTissue = 'gm' | 'wm' | 'csf'
export type ViewerArtifactMode = 'mesh' | 'wireframe'

export type BrainViewerItem = {
  id: string
  name: string
  tissue: ViewerTissue
  mode: ViewerArtifactMode
  objectUrl: string
  /**
   * Keep colors/materials authored inside the GLB. Useful for comparison GLBs
   * where the backend encodes baseline/target colors directly.
   */
  preserveMaterials?: boolean
}

type TissueControls = Record<ViewerTissue, {
  visible: boolean
  opacity: number
  color: string
}>

type ViewerTransform = {
  scale: number
  rotateX: number
  rotateY: number
  rotateZ: number
}

type GridUnit = 'mm' | 'cm'

const tissueLabels: Record<ViewerTissue, string> = {
  gm: 'Gray matter',
  wm: 'White matter',
  csf: 'CSF',
}

const defaultTissueControls: TissueControls = {
  gm: { visible: true, opacity: 0.58, color: '#f97316' },
  wm: { visible: true, opacity: 0.46, color: '#e2e8f0' },
  csf: { visible: true, opacity: 0.36, color: '#38bdf8' },
}

const defaultTransform: ViewerTransform = {
  scale: 1,
  rotateX: 0,
  rotateY: 0,
  rotateZ: 0,
}

export function inferViewerTissueFromName(name: string, metadataTissue?: unknown): ViewerTissue | null {
  if (metadataTissue === 'gm' || metadataTissue === 'wm' || metadataTissue === 'csf') {
    return metadataTissue
  }

  const lower = name.toLowerCase()
  if (lower.includes('gray') || lower.includes('_gm') || lower.includes('gm_') || lower.includes('-gm')) {
    return 'gm'
  }
  if (lower.includes('white') || lower.includes('_wm') || lower.includes('wm_') || lower.includes('-wm')) {
    return 'wm'
  }
  if (lower.includes('csf') || lower.includes('cerebrospinal')) {
    return 'csf'
  }
  return null
}

export function inferViewerModeFromName(nameOrKind: string): ViewerArtifactMode | null {
  const lower = nameOrKind.toLowerCase()
  if (lower.includes('wireframe')) {
    return 'wireframe'
  }
  if (lower.includes('mesh') || lower.endsWith('.glb')) {
    return 'mesh'
  }
  return null
}

export function isGlbName(name: string, mimeType?: string | null): boolean {
  return name.toLowerCase().endsWith('.glb') || mimeType === 'model/gltf-binary'
}

function ModelLayer({
  item,
  controls,
  transform,
  showMeshes,
  showWireframes,
  doubleSided,
}: {
  item: BrainViewerItem
  controls: TissueControls
  transform: ViewerTransform
  showMeshes: boolean
  showWireframes: boolean
  doubleSided: boolean
}) {
  const gltf = useGLTF(item.objectUrl)
  const control = controls[item.tissue]
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
        cloned.side = doubleSided ? THREE.DoubleSide : THREE.FrontSide

        if (item.preserveMaterials) {
          return cloned
        }

        const opacity = item.mode === 'wireframe'
          ? Math.min(1, Math.max(0.25, control.opacity + 0.25))
          : control.opacity

        cloned.transparent = opacity < 1 || item.mode === 'wireframe'
        cloned.opacity = opacity
        cloned.depthWrite = opacity >= 0.95

        const materialWithColor = cloned as THREE.Material & { color?: THREE.Color }
        if (materialWithColor.color instanceof THREE.Color) {
          materialWithColor.color.set(control.color)
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
  }, [control.color, control.opacity, doubleSided, gltf.scene, item.mode])

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

function AutoRotateGroup({
  enabled,
  resetSignal,
  children,
}: {
  enabled: boolean
  resetSignal: number
  children: ReactNode
}) {
  const groupRef = useRef<THREE.Group>(null)

  useEffect(() => {
    if (groupRef.current) {
      groupRef.current.rotation.set(0, 0, 0)
    }
  }, [resetSignal])

  useFrame((_, delta) => {
    if (enabled && groupRef.current) {
      groupRef.current.rotation.y += delta * 0.28
    }
  })

  return <group ref={groupRef}>{children}</group>
}

function formatGridLabel(valueMm: number, unit: GridUnit): string {
  if (unit === 'cm') {
    return `${Number((valueMm / 10).toFixed(1))} cm`
  }
  return `${Math.round(valueMm)} mm`
}

function MeasurementGrid({ unit }: { unit: GridUnit }) {
  const sizeMm = 260
  const stepMm = unit === 'cm' ? 10 : 20
  const divisions = sizeMm / stepMm
  const half = sizeMm / 2
  const z = -70
  const values: number[] = []

  for (let value = -half; value <= half + 0.1; value += stepMm) {
    if (Math.abs(value) > 0.1 && Math.abs(value) % (unit === 'cm' ? 50 : 40) < 0.1) {
      values.push(value)
    }
  }

  return (
    <group>
      <gridHelper args={[sizeMm, divisions, '#1d4ed8', '#1f2937']} position={[0, 0, z]} />
      {values.map((value) => (
        <group key={value}>
          <Html position={[value, -half - 10, z]} center wrapperClass="grid-label-wrap">
            <span className="grid-label">{formatGridLabel(value, unit)}</span>
          </Html>
          <Html position={[-half - 16, value, z]} center wrapperClass="grid-label-wrap">
            <span className="grid-label">{formatGridLabel(value, unit)}</span>
          </Html>
        </group>
      ))}
    </group>
  )
}

function BrainGlbScene({
  items,
  controls,
  transform,
  showMeshes,
  showWireframes,
  doubleSided,
  autoRotate,
  resetSignal,
  gridUnit,
}: {
  items: BrainViewerItem[]
  controls: TissueControls
  transform: ViewerTransform
  showMeshes: boolean
  showWireframes: boolean
  doubleSided: boolean
  autoRotate: boolean
  resetSignal: number
  gridUnit: GridUnit
}) {
  return (
    <Canvas camera={{ position: [0, -260, 130], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={['#08111f']} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[80, -120, 160]} intensity={2.1} />
      <directionalLight position={[-120, 80, -80]} intensity={0.9} />
      <MeasurementGrid unit={gridUnit} />
      <axesHelper args={[60]} />
      <Suspense fallback={null}>
        <Center>
          <AutoRotateGroup enabled={autoRotate} resetSignal={resetSignal}>
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

export function Brain3DViewer({
  items,
  title,
  subtitle,
  loadingText = 'Loading GLB artifacts...',
  isLoading = false,
  error = null,
  onReload,
}: {
  items: BrainViewerItem[]
  title: string
  subtitle: string
  loadingText?: string
  isLoading?: boolean
  error?: string | null
  onReload?: () => void
}) {
  const [controls, setControls] = useState<TissueControls>(defaultTissueControls)
  const [showMeshes, setShowMeshes] = useState(true)
  const [showWireframes, setShowWireframes] = useState(true)
  const [doubleSided, setDoubleSided] = useState(true)
  const [autoRotate, setAutoRotate] = useState(false)
  const [transform, setTransform] = useState<ViewerTransform>(defaultTransform)
  const [gridUnit, setGridUnit] = useState<GridUnit>('mm')
  const [resetSignal, setResetSignal] = useState(0)

  function updateTissue(tissue: ViewerTissue, patch: Partial<TissueControls[ViewerTissue]>) {
    setControls((current) => ({
      ...current,
      [tissue]: {
        ...current[tissue],
        ...patch,
      },
    }))
  }

  function resetTransform() {
    setTransform(defaultTransform)
    setResetSignal((current) => current + 1)
  }

  const visibleCount = items.filter((item) => {
    const tissueControl = controls[item.tissue]
    return tissueControl.visible && (item.mode === 'mesh' ? showMeshes : showWireframes)
  }).length

  const hasMeshes = items.some((item) => item.mode === 'mesh')
  const hasWireframes = items.some((item) => item.mode === 'wireframe')

  return (
    <section className="viewer-layout">
      <aside className="card stack viewer-controls-panel">
        <div>
          <p className="eyebrow">Scene controls</p>
          <h2>{title}</h2>
          <p className="muted small-note">{subtitle}</p>
        </div>

        {onReload && (
          <button type="button" className="secondary" onClick={onReload} disabled={isLoading}>
            Reload GLBs
          </button>
        )}

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
          {(['gm', 'wm', 'csf'] as ViewerTissue[]).map((tissue) => (
            <div className="tissue-control" key={tissue}>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={controls[tissue].visible}
                  onChange={(event) => updateTissue(tissue, { visible: event.target.checked })}
                />
                <span className="tissue-dot" style={{ background: controls[tissue].color }} />
                {tissueLabels[tissue]}
              </label>
              <label className="range-label">
                Color
                <input
                  type="color"
                  value={controls[tissue].color}
                  onChange={(event) => updateTissue(tissue, { color: event.target.value })}
                />
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
          <h3>Grid scale</h3>
          <label>
            Unit
            <select value={gridUnit} onChange={(event) => setGridUnit(event.target.value as GridUnit)}>
              <option value="mm">millimetres</option>
              <option value="cm">centimetres</option>
            </select>
          </label>
          <p className="muted small-note">
            The grid assumes mesh coordinates are in millimetres. In cm mode, labels are converted from mm to cm.
          </p>
        </div>

        <div className="stack compact-stack">
          <div className="row-between">
            <h3>Model transform</h3>
            <button type="button" className="secondary mini-button" onClick={resetTransform}>Reset</button>
          </div>
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
          <span className="muted small-note">Runtime controls are applied in WebGL. The GLB files are not re-exported.</span>
        </div>
        {error && <p className="error-text">{error}</p>}
        {isLoading && <p className="muted">{loadingText}</p>}
        <div className="viewer-canvas-wrap">
          {items.length > 0 ? (
            <BrainGlbScene
              items={items}
              controls={controls}
              transform={transform}
              showMeshes={showMeshes}
              showWireframes={showWireframes}
              doubleSided={doubleSided}
              autoRotate={autoRotate}
              resetSignal={resetSignal}
              gridUnit={gridUnit}
            />
          ) : (
            <div className="viewer-empty-state">
              <h2>No GLB artifacts found</h2>
              <p className="muted">Run mesh analysis or public processing first, then return to this viewer.</p>
            </div>
          )}
        </div>
      </section>
    </section>
  )
}
