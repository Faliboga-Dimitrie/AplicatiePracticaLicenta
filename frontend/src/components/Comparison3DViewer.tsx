import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Center, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { createDefaultViewerTransform, ViewerTransformControls } from './ViewerTransformControls'
import type { ViewerTransform } from './ViewerTransformControls'

type TransformTarget = 'both' | 'unchanged' | 'changed'
type LayerKind = 'unchanged' | 'changed'
type ComparisonTransforms = Record<TransformTarget, ViewerTransform>

const transformTargetOptions: Array<{ value: TransformTarget; label: string }> = [
  { value: 'both', label: 'Both layers' },
  { value: 'unchanged', label: 'Unchanged layer' },
  { value: 'changed', label: 'Changed layer' },
]

function createDefaultComparisonTransforms(): ComparisonTransforms {
  return {
    both: createDefaultViewerTransform(),
    unchanged: createDefaultViewerTransform(),
    changed: createDefaultViewerTransform(),
  }
}

function MeasurementGrid() {
  return <gridHelper args={[260, 26, '#1d4ed8', '#1f2937']} position={[0, 0, -70]} />
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

function classifyLayer(name: string): LayerKind | null {
  const lower = name.toLowerCase()
  if (lower.includes('unchanged')) return 'unchanged'
  if (lower.includes('changed')) return 'changed'
  return null
}

function cloneMaterialWithStyle(material: THREE.Material, color: string, opacity: number) {
  const cloned = material.clone()
  cloned.side = THREE.DoubleSide
  cloned.transparent = opacity < 1
  cloned.opacity = opacity
  cloned.depthWrite = opacity >= 0.95

  const colored = cloned as THREE.Material & { color?: THREE.Color }
  if (colored.color instanceof THREE.Color) {
    colored.color.set(color)
  }

  return cloned
}

function applyGroupStyle(group: THREE.Group, color: string, opacity: number) {
  group.traverse((object) => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.LineSegments)) return

    const sourceMaterial = object.material
    const materials = Array.isArray(sourceMaterial) ? sourceMaterial : [sourceMaterial]
    const styledMaterials = materials.map((material) => cloneMaterialWithStyle(material, color, opacity))
    object.material = Array.isArray(sourceMaterial) ? styledMaterials : styledMaterials[0]
  })
}

function disposeStyledMaterials(group: THREE.Group) {
  group.traverse((object) => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.LineSegments)) return
    const materials = Array.isArray(object.material) ? object.material : [object.material]
    materials.forEach((material) => material.dispose())
  })
}

function transformProps(transform: ViewerTransform) {
  return {
    scale: transform.scale,
    rotation: [transform.rotateX, transform.rotateY, transform.rotateZ] as [number, number, number],
    position: [transform.translateX, transform.translateY, transform.translateZ] as [number, number, number],
  }
}

function ComparisonScene({
  objectUrl,
  unchangedColor,
  changedColor,
  unchangedOpacity,
  changedOpacity,
  autoRotate,
  resetSignal,
  transforms,
  backgroundColor,
}: {
  objectUrl: string
  unchangedColor: string
  changedColor: string
  unchangedOpacity: number
  changedOpacity: number
  autoRotate: boolean
  resetSignal: number
  transforms: ComparisonTransforms
  backgroundColor: string
}) {
  const gltf = useGLTF(objectUrl)

  const { unchangedGroup, changedGroup } = useMemo(() => {
    const unchanged = new THREE.Group()
    const changed = new THREE.Group()

    gltf.scene.updateMatrixWorld(true)
    gltf.scene.traverse((object) => {
      if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.LineSegments)) return

      const layer = classifyLayer(object.name)
      if (!layer) return

      const clone = object.clone()
      if (layer === 'changed') {
        changed.add(clone)
      } else {
        unchanged.add(clone)
      }
    })

    applyGroupStyle(unchanged, unchangedColor, unchangedOpacity)
    applyGroupStyle(changed, changedColor, changedOpacity)

    return { unchangedGroup: unchanged, changedGroup: changed }
  }, [changedColor, changedOpacity, gltf.scene, unchangedColor, unchangedOpacity])

  useEffect(() => {
    return () => {
      disposeStyledMaterials(unchangedGroup)
      disposeStyledMaterials(changedGroup)
    }
  }, [changedGroup, unchangedGroup])

  const bothProps = transformProps(transforms.both)
  const unchangedProps = transformProps(transforms.unchanged)
  const changedProps = transformProps(transforms.changed)

  return (
    <Canvas camera={{ position: [0, -260, 130], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={[backgroundColor]} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[80, -120, 160]} intensity={2.1} />
      <directionalLight position={[-120, 80, -80]} intensity={0.9} />
      <MeasurementGrid />
      <axesHelper args={[60]} />
      <Suspense fallback={null}>
        <Center>
          <group {...bothProps}>
            <AutoRotateGroup enabled={autoRotate} resetSignal={resetSignal}>
              <primitive object={unchangedGroup} {...unchangedProps} />
              <primitive object={changedGroup} {...changedProps} />
            </AutoRotateGroup>
          </group>
        </Center>
      </Suspense>
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
    </Canvas>
  )
}

export function Comparison3DViewer({
  objectUrl,
  title,
  subtitle,
  loadingText = 'Loading comparison...',
  isLoading = false,
  error = null,
  onReload,
}: {
  objectUrl: string | null
  title: string
  subtitle: string
  loadingText?: string
  isLoading?: boolean
  error?: string | null
  onReload?: () => void
}) {
  const [unchangedColor, setUnchangedColor] = useState('#508cff')
  const [changedColor, setChangedColor] = useState('#ff2d2d')
  const [unchangedOpacity, setUnchangedOpacity] = useState(0.28)
  const [changedOpacity, setChangedOpacity] = useState(0.95)
  const [autoRotate, setAutoRotate] = useState(false)
  const [transforms, setTransforms] = useState<ComparisonTransforms>(() => createDefaultComparisonTransforms())
  const [activeTransformTarget, setActiveTransformTarget] = useState<TransformTarget>('both')
  const [backgroundColor, setBackgroundColor] = useState('#000000')
  const [resetSignal, setResetSignal] = useState(0)

  function updateTransform(target: TransformTarget, transform: ViewerTransform) {
    setTransforms((current) => ({ ...current, [target]: transform }))
  }

  function resetActiveTransform() {
    setTransforms((current) => ({ ...current, [activeTransformTarget]: createDefaultViewerTransform() }))
    setResetSignal((current) => current + 1)
  }

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
            {isLoading ? 'Building...' : 'Reload comparison'}
          </button>
        )}

        <div className="stack compact-stack">
          <label className="inline-field">
            Unchanged opacity
            <input type="range" min="0" max="1" step="0.05" value={unchangedOpacity} onChange={(event) => setUnchangedOpacity(Number(event.target.value))} />
            <span className="muted small-note">{Math.round(unchangedOpacity * 100)}%</span>
          </label>
          <label className="inline-field">
            Changed opacity
            <input type="range" min="0" max="1" step="0.05" value={changedOpacity} onChange={(event) => setChangedOpacity(Number(event.target.value))} />
            <span className="muted small-note">{Math.round(changedOpacity * 100)}%</span>
          </label>
          <label className="inline-field">
            Unchanged color
            <input type="color" value={unchangedColor} onChange={(event) => setUnchangedColor(event.target.value)} />
          </label>
          <label className="inline-field">
            Changed color
            <input type="color" value={changedColor} onChange={(event) => setChangedColor(event.target.value)} />
          </label>
          <label className="inline-field color-inline-field">
            Background
            <input type="color" value={backgroundColor} onChange={(event) => setBackgroundColor(event.target.value)} />
          </label>
          <label className="checkbox-row inline-checkbox">
            <input type="checkbox" checked={autoRotate} onChange={(event) => setAutoRotate(event.target.checked)} />
            auto rotate
          </label>
        </div>

        <ViewerTransformControls
          title="Model position"
          targetLabel="Move layer"
          activeTarget={activeTransformTarget}
          targetOptions={transformTargetOptions}
          transform={transforms[activeTransformTarget]}
          onActiveTargetChange={(target) => setActiveTransformTarget(target as TransformTarget)}
          onTransformChange={(transform) => updateTransform(activeTransformTarget, transform)}
          onReset={resetActiveTransform}
        />
      </aside>

      <div className="viewer-stage card" style={{ backgroundColor }}>
        {isLoading && <div className="viewer-overlay"><p>{loadingText}</p></div>}
        {!isLoading && error && <div className="viewer-empty-state"><p className="error-text">{error}</p></div>}
        {!isLoading && !error && objectUrl && (
          <ComparisonScene
            objectUrl={objectUrl}
            unchangedColor={unchangedColor}
            changedColor={changedColor}
            unchangedOpacity={unchangedOpacity}
            changedOpacity={changedOpacity}
            autoRotate={autoRotate}
            resetSignal={resetSignal}
            transforms={transforms}
            backgroundColor={backgroundColor}
          />
        )}
        {!isLoading && !error && !objectUrl && <div className="viewer-empty-state"><p className="muted">No comparison loaded yet.</p></div>}
      </div>
    </section>
  )
}
