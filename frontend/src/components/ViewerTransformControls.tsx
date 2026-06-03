/* eslint-disable react-refresh/only-export-components */
export type ViewerTransform = {
  scale: number
  rotateX: number
  rotateY: number
  rotateZ: number
  translateX: number
  translateY: number
  translateZ: number
}

export const defaultViewerTransform: ViewerTransform = {
  scale: 1,
  rotateX: 0,
  rotateY: 0,
  rotateZ: 0,
  translateX: 0,
  translateY: 0,
  translateZ: 0,
}

export function createDefaultViewerTransform(): ViewerTransform {
  return { ...defaultViewerTransform }
}

type TransformField = keyof ViewerTransform

type TransformTargetOption = {
  value: string
  label: string
}

function radiansToDegrees(value: number): number {
  return Math.round((value * 180) / Math.PI)
}

function degreesToRadians(value: number): number {
  return (value * Math.PI) / 180
}

function formatDegrees(value: number): string {
  return `${radiansToDegrees(value)}°`
}

function boundedNumber(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback
}

export function ViewerTransformControls({
  title = 'Model position',
  targetLabel = 'Apply to',
  activeTarget,
  targetOptions,
  transform,
  onActiveTargetChange,
  onTransformChange,
  onReset,
}: {
  title?: string
  targetLabel?: string
  activeTarget: string
  targetOptions: TransformTargetOption[]
  transform: ViewerTransform
  onActiveTargetChange: (target: string) => void
  onTransformChange: (transform: ViewerTransform) => void
  onReset: () => void
}) {
  function updateField(field: TransformField, value: number) {
    onTransformChange({
      ...transform,
      [field]: boundedNumber(value, defaultViewerTransform[field]),
    })
  }

  function updateRotationField(field: 'rotateX' | 'rotateY' | 'rotateZ', degrees: number) {
    updateField(field, degreesToRadians(boundedNumber(degrees, 0)))
  }

  return (
    <div className="stack compact-stack">
      <div className="row-between">
        <h3>{title}</h3>
        <button type="button" className="secondary mini-button" onClick={onReset}>Reset</button>
      </div>

      <label className="range-label">
        {targetLabel}
        <select value={activeTarget} onChange={(event) => onActiveTargetChange(event.target.value)}>
          {targetOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>

      <div className="transform-control-grid">
        <label className="transform-field">
          <span>Scale</span>
          <div className="transform-input-row">
            <input
              type="range"
              min="0.1"
              max="3"
              step="0.05"
              value={transform.scale}
              onChange={(event) => updateField('scale', Number(event.target.value))}
            />
            <input
              type="number"
              min="0.1"
              max="5"
              step="0.05"
              value={transform.scale}
              onChange={(event) => updateField('scale', Number(event.target.value))}
              aria-label="Scale value"
            />
          </div>
        </label>

        <label className="transform-field">
          <span>Move X</span>
          <div className="transform-input-row">
            <input
              type="range"
              min="-200"
              max="200"
              step="1"
              value={transform.translateX}
              onChange={(event) => updateField('translateX', Number(event.target.value))}
            />
            <input
              type="number"
              min="-500"
              max="500"
              step="1"
              value={transform.translateX}
              onChange={(event) => updateField('translateX', Number(event.target.value))}
              aria-label="Move X value"
            />
          </div>
        </label>

        <label className="transform-field">
          <span>Move Y</span>
          <div className="transform-input-row">
            <input
              type="range"
              min="-200"
              max="200"
              step="1"
              value={transform.translateY}
              onChange={(event) => updateField('translateY', Number(event.target.value))}
            />
            <input
              type="number"
              min="-500"
              max="500"
              step="1"
              value={transform.translateY}
              onChange={(event) => updateField('translateY', Number(event.target.value))}
              aria-label="Move Y value"
            />
          </div>
        </label>

        <label className="transform-field">
          <span>Move Z</span>
          <div className="transform-input-row">
            <input
              type="range"
              min="-200"
              max="200"
              step="1"
              value={transform.translateZ}
              onChange={(event) => updateField('translateZ', Number(event.target.value))}
            />
            <input
              type="number"
              min="-500"
              max="500"
              step="1"
              value={transform.translateZ}
              onChange={(event) => updateField('translateZ', Number(event.target.value))}
              aria-label="Move Z value"
            />
          </div>
        </label>

        <label className="transform-field">
          <span>Rotate X <small>{formatDegrees(transform.rotateX)}</small></span>
          <div className="transform-input-row">
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={radiansToDegrees(transform.rotateX)}
              onChange={(event) => updateRotationField('rotateX', Number(event.target.value))}
            />
            <input
              type="number"
              min="-360"
              max="360"
              step="1"
              value={radiansToDegrees(transform.rotateX)}
              onChange={(event) => updateRotationField('rotateX', Number(event.target.value))}
              aria-label="Rotate X value in degrees"
            />
          </div>
        </label>

        <label className="transform-field">
          <span>Rotate Y <small>{formatDegrees(transform.rotateY)}</small></span>
          <div className="transform-input-row">
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={radiansToDegrees(transform.rotateY)}
              onChange={(event) => updateRotationField('rotateY', Number(event.target.value))}
            />
            <input
              type="number"
              min="-360"
              max="360"
              step="1"
              value={radiansToDegrees(transform.rotateY)}
              onChange={(event) => updateRotationField('rotateY', Number(event.target.value))}
              aria-label="Rotate Y value in degrees"
            />
          </div>
        </label>

        <label className="transform-field">
          <span>Rotate Z <small>{formatDegrees(transform.rotateZ)}</small></span>
          <div className="transform-input-row">
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={radiansToDegrees(transform.rotateZ)}
              onChange={(event) => updateRotationField('rotateZ', Number(event.target.value))}
            />
            <input
              type="number"
              min="-360"
              max="360"
              step="1"
              value={radiansToDegrees(transform.rotateZ)}
              onChange={(event) => updateRotationField('rotateZ', Number(event.target.value))}
              aria-label="Rotate Z value in degrees"
            />
          </div>
        </label>
      </div>
    </div>
  )
}
