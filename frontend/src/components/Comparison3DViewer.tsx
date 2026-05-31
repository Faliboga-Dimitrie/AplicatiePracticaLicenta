import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Center, Html, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

type ViewerTransform = {
  scale: number
  rotateX: number
  rotateY: number
  rotateZ: number
}

type GridUnit = 'mm' | 'cm'
type TransformTarget = 'unchanged' | 'changed' | 'both'
type LayerKind = 'unchanged' | 'changed'

const defaultTransform: ViewerTransform = {
  scale: 1,
  rotateX: 0,
  rotateY: 0,
  rotateZ: 0,
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

function AutoRotateGroup({ enabled, resetSignal, children }: { enabled: boolean; resetSignal: number; children: ReactNode }) {
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

function ComparisonScene({
  objectUrl,
  unchangedColor,
  changedColor,
  unchangedOpacity,
  changedOpacity,
  autoRotate,
  resetSignal,
  gridUnit,
  transform,
  transformTarget,
}: {
  objectUrl: string
  unchangedColor: string
  changedColor: string
  unchangedOpacity: number
  changedOpacity: number
  autoRotate: boolean
  resetSignal: number
  gridUnit: GridUnit
  transform: ViewerTransform
  transformTarget: TransformTarget
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

  const unchangedRotation: [number, number, number] = transformTarget === 'changed'
    ? [0, 0, 0]
    : [transform.rotateX, transform.rotateY, transform.rotateZ]
  const changedRotation: [number, number, number] = transformTarget === 'unchanged'
    ? [0, 0, 0]
    : [transform.rotateX, transform.rotateY, transform.rotateZ]
  const unchangedScale = transformTarget === 'changed' ? 1 : transform.scale
  const changedScale = transformTarget === 'unchanged' ? 1 : transform.scale

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
            <primitive object={unchangedGroup} scale={unchangedScale} rotation={unchangedRotation} />
            <primitive object={changedGroup} scale={changedScale} rotation={changedRotation} />
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
  const [transform, setTransform] = useState<ViewerTransform>(defaultTransform)
  const [transformTarget, setTransformTarget] = useState<TransformTarget>('both')
  const [gridUnit, setGridUnit] = useState<GridUnit>('mm')
  const [resetSignal, setResetSignal] = useState(0)

  function resetTransform() {
    setTransform(defaultTransform)
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
          <label className="checkbox-row inline-checkbox">
            <input type="checkbox" checked={autoRotate} onChange={(event) => setAutoRotate(event.target.checked)} />
            auto rotate
          </label>
          <label className="inline-field">
            Grid scale
            <select value={gridUnit} onChange={(event) => setGridUnit(event.target.value as GridUnit)}>
              <option value="mm">millimetres</option>
              <option value="cm">centimetres</option>
            </select>
          </label>
        </div>

        <div className="stack compact-stack">
          <h3>Model transform</h3>
          <label className="inline-field">
            Apply to
            <select value={transformTarget} onChange={(event) => setTransformTarget(event.target.value as TransformTarget)}>
              <option value="both">both layers</option>
              <option value="unchanged">unchanged layer</option>
              <option value="changed">changed layer</option>
            </select>
          </label>
          <label className="inline-field">
            Scale
            <input type="range" min="0.3" max="2.5" step="0.05" value={transform.scale} onChange={(event) => setTransform((current) => ({ ...current, scale: Number(event.target.value) }))} />
            <span className="muted small-note">{transform.scale.toFixed(2)}×</span>
          </label>
          <label className="inline-field">
            Rotate X
            <input type="range" min={-Math.PI} max={Math.PI} step="0.05" value={transform.rotateX} onChange={(event) => setTransform((current) => ({ ...current, rotateX: Number(event.target.value) }))} />
            <span className="muted small-note">{formatRadians(transform.rotateX)}</span>
          </label>
          <label className="inline-field">
            Rotate Y
            <input type="range" min={-Math.PI} max={Math.PI} step="0.05" value={transform.rotateY} onChange={(event) => setTransform((current) => ({ ...current, rotateY: Number(event.target.value) }))} />
            <span className="muted small-note">{formatRadians(transform.rotateY)}</span>
          </label>
          <label className="inline-field">
            Rotate Z
            <input type="range" min={-Math.PI} max={Math.PI} step="0.05" value={transform.rotateZ} onChange={(event) => setTransform((current) => ({ ...current, rotateZ: Number(event.target.value) }))} />
            <span className="muted small-note">{formatRadians(transform.rotateZ)}</span>
          </label>
          <button type="button" className="secondary" onClick={resetTransform}>Reset transform</button>
        </div>
      </aside>

      <div className="viewer-stage card">
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
            gridUnit={gridUnit}
            transform={transform}
            transformTarget={transformTarget}
          />
        )}
        {!isLoading && !error && !objectUrl && <div className="viewer-empty-state"><p className="muted">No comparison loaded yet.</p></div>}
      </div>
    </section>
  )
}
