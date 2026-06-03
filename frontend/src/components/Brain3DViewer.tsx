import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Center, OrbitControls, useGLTF, useProgress } from '@react-three/drei'
import * as THREE from 'three'
import type { BrainViewerItem, ViewerTissue } from './brainViewerUtils'
import { createDefaultViewerTransform, ViewerTransformControls } from './ViewerTransformControls'
import type { ViewerTransform } from './ViewerTransformControls'

type TissueControls = Record<ViewerTissue, {
  visible: boolean
  opacity: number
  color: string
}>

type TissueTransforms = Record<ViewerTissue, ViewerTransform>

const tissueLabels: Record<ViewerTissue, string> = {
  gm: 'Gray matter',
  wm: 'White matter',
  csf: 'CSF',
}

const tissueTransformOptions: Array<{ value: ViewerTissue; label: string }> = [
  { value: 'gm', label: 'Gray matter' },
  { value: 'wm', label: 'White matter' },
  { value: 'csf', label: 'CSF' },
]

const defaultTissueControls: TissueControls = {
  gm: { visible: true, opacity: 0.58, color: '#f97316' },
  wm: { visible: true, opacity: 0.46, color: '#e2e8f0' },
  csf: { visible: true, opacity: 0.36, color: '#38bdf8' },
}

function createDefaultTissueTransforms(): TissueTransforms {
  return {
    gm: createDefaultViewerTransform(),
    wm: createDefaultViewerTransform(),
    csf: createDefaultViewerTransform(),
  }
}

function ModelLayer({
  item,
  controls,
  transform,
  showMeshes,
  doubleSided,
}: {
  item: BrainViewerItem
  controls: TissueControls
  transform: ViewerTransform
  showMeshes: boolean
  doubleSided: boolean
}) {
  const gltf = useGLTF(item.objectUrl)
  const control = controls[item.tissue]
  const shouldShow = control.visible && showMeshes

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

        const opacity = control.opacity

        cloned.transparent = opacity < 1
        cloned.opacity = opacity
        cloned.depthWrite = opacity >= 0.95

        const materialWithColor = cloned as THREE.Material & { color?: THREE.Color }
        if (materialWithColor.color instanceof THREE.Color) {
          materialWithColor.color.set(control.color)
        }

        return cloned
      })

      object.material = Array.isArray(sourceMaterial) ? clonedMaterials : clonedMaterials[0]
    })
    return clone
  }, [control.color, control.opacity, doubleSided, gltf.scene, item.preserveMaterials])

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
      position={[transform.translateX, transform.translateY, transform.translateZ]}
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

function MeasurementGrid() {
  return <gridHelper args={[260, 26, '#1d4ed8', '#1f2937']} position={[0, 0, -70]} />
}

function SceneReadySignal({
  itemCount,
  onSceneReady,
}: {
  itemCount: number
  onSceneReady?: () => void
}) {
  const { active, progress } = useProgress()
  const hasNotifiedRef = useRef(false)

  useEffect(() => {
    if (itemCount <= 0 || !onSceneReady || hasNotifiedRef.current) {
      return
    }

    if (!active && progress >= 100) {
      hasNotifiedRef.current = true
      onSceneReady()
    }
  }, [active, itemCount, onSceneReady, progress])

  return null
}

function BrainGlbScene({
  items,
  controls,
  transforms,
  showMeshes,
  doubleSided,
  autoRotate,
  resetSignal,
  backgroundColor,
  onSceneReady,
}: {
  items: BrainViewerItem[]
  controls: TissueControls
  transforms: TissueTransforms
  showMeshes: boolean
  doubleSided: boolean
  autoRotate: boolean
  resetSignal: number
  backgroundColor: string
  onSceneReady?: () => void
}) {
  return (
    <Canvas camera={{ position: [0, -260, 130], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={[backgroundColor]} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[80, -120, 160]} intensity={2.1} />
      <directionalLight position={[-120, 80, -80]} intensity={0.9} />
      <MeasurementGrid />
      <axesHelper args={[60]} />
      <SceneReadySignal itemCount={items.length} onSceneReady={onSceneReady} />
      <Suspense fallback={null}>
        <Center>
          <AutoRotateGroup enabled={autoRotate} resetSignal={resetSignal}>
            {items.map((item) => (
              <ModelLayer
                key={item.id}
                item={item}
                controls={controls}
                transform={transforms[item.tissue]}
                showMeshes={showMeshes}
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

export function Brain3DViewer({
  items,
  title,
  subtitle,
  loadingText = 'Loading 3D model...',
  isLoading = false,
  error = null,
  onReload,
  controlMode = 'full',
  onSceneReady,
}: {
  items: BrainViewerItem[]
  title: string
  subtitle: string
  loadingText?: string
  isLoading?: boolean
  error?: string | null
  onReload?: () => void
  controlMode?: 'full' | 'comparison'
  onSceneReady?: () => void
}) {
  const [controls, setControls] = useState<TissueControls>(defaultTissueControls)
  const [showMeshes, setShowMeshes] = useState(true)
  const [doubleSided, setDoubleSided] = useState(true)
  const [autoRotate, setAutoRotate] = useState(false)
  const [transforms, setTransforms] = useState<TissueTransforms>(() => createDefaultTissueTransforms())
  const [activeTransformTissue, setActiveTransformTissue] = useState<ViewerTissue>('gm')
  const [backgroundColor, setBackgroundColor] = useState('#000000')
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

  function updateTransform(tissue: ViewerTissue, transform: ViewerTransform) {
    setTransforms((current) => ({ ...current, [tissue]: transform }))
  }

  function resetActiveTransform() {
    setTransforms((current) => ({ ...current, [activeTransformTissue]: createDefaultViewerTransform() }))
    setResetSignal((current) => current + 1)
  }

  const visibleCount = items.filter((item) => {
    const tissueControl = controls[item.tissue]
    return tissueControl.visible && showMeshes
  }).length

  const hasMeshes = items.some((item) => item.mode === 'mesh')
  const showLayerControls = controlMode === 'full'

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
            Reload model
          </button>
        )}

        <div className="viewer-toggle-grid">
          {showLayerControls && (
            <>
              <label className="checkbox-row">
                <input type="checkbox" checked={showMeshes} disabled={!hasMeshes} onChange={(event) => setShowMeshes(event.target.checked)} />
                3D tissue layers
              </label>
              <label className="checkbox-row">
                <input type="checkbox" checked={doubleSided} onChange={(event) => setDoubleSided(event.target.checked)} />
                Show inside surfaces
              </label>
            </>
          )}
          <label className="checkbox-row">
            <input type="checkbox" checked={autoRotate} onChange={(event) => setAutoRotate(event.target.checked)} />
            Auto rotate
          </label>
        </div>

        <div className="stack compact-stack">
          <h3>Scene background</h3>
          <label className="inline-field color-inline-field">
            Background
            <input type="color" value={backgroundColor} onChange={(event) => setBackgroundColor(event.target.value)} />
          </label>
        </div>

        {showLayerControls && (
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
        )}

        <ViewerTransformControls
          title="Model position"
          targetLabel="Move tissue"
          activeTarget={activeTransformTissue}
          targetOptions={tissueTransformOptions}
          transform={transforms[activeTransformTissue]}
          onActiveTargetChange={(target) => setActiveTransformTissue(target as ViewerTissue)}
          onTransformChange={(transform) => updateTransform(activeTransformTissue, transform)}
          onReset={resetActiveTransform}
        />

        <div className="viewer-help-card">
          <strong>Orbit controls</strong>
          <p>Drag to rotate, scroll to zoom, right-drag to pan. Use model position to align each tissue layer independently.</p>
        </div>
      </aside>

      <section className="card viewer-canvas-card">
        <div className="viewer-canvas-toolbar">
          <span className="badge">{visibleCount}/{items.length} layers visible</span>
          <span className="muted small-note">Display changes affect only this preview.</span>
        </div>
        {error && <p className="error-text viewer-message-pad">{error}</p>}
        {isLoading && <p className="muted viewer-message-pad">{loadingText}</p>}
        <div className="viewer-canvas-wrap" style={{ backgroundColor }}>
          {items.length > 0 ? (
            <BrainGlbScene
              items={items}
              controls={controls}
              transforms={transforms}
              showMeshes={showMeshes}
              doubleSided={doubleSided}
              autoRotate={autoRotate}
              resetSignal={resetSignal}
              backgroundColor={backgroundColor}
              onSceneReady={onSceneReady}
            />
          ) : (
            <div className="viewer-empty-state">
              <h2>No 3D model found</h2>
              <p className="muted">Create the 3D model first, then return to this viewer.</p>
            </div>
          )}
        </div>
      </section>
    </section>
  )
}
