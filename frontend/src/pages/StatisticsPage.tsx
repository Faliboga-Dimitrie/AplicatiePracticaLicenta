import { useEffect, useMemo, useState } from 'react'
import { apiMessage } from '../api/client'
import { getCaseMetrics } from '../api/metricsApi'
import type { CaseMetricsResponse, TissueKey } from '../types/api'

type StatisticsPageProps = {
  caseId: number
  onBack: () => void
  onOpenViewer?: () => void
}

type MetricUnit = 'mm' | 'cm'

const TISSUES: Array<{ key: TissueKey; label: string; volumeKey: string; surfaceKey: string }> = [
  { key: 'csf', label: 'CSF', volumeKey: 'csf_mm3', surfaceKey: 'csf_mm2' },
  { key: 'gm', label: 'Gray matter', volumeKey: 'gm_mm3', surfaceKey: 'gm_mm2' },
  { key: 'wm', label: 'White matter', volumeKey: 'wm_mm3', surfaceKey: 'wm_mm2' },
]

function formatNumber(value: number | null | undefined, fractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: fractionDigits }).format(value)
}

function convertVolume(valueMm3: number | undefined, unit: MetricUnit): number | null {
  if (valueMm3 === undefined) return null
  return unit === 'cm' ? valueMm3 / 1000 : valueMm3
}

function convertSurface(valueMm2: number | undefined, unit: MetricUnit): number | null {
  if (valueMm2 === undefined) return null
  return unit === 'cm' ? valueMm2 / 100 : valueMm2
}

function volumeUnitLabel(unit: MetricUnit): string {
  return unit === 'cm' ? 'cm³' : 'mm³'
}

function surfaceUnitLabel(unit: MetricUnit): string {
  return unit === 'cm' ? 'cm²' : 'mm²'
}

function percentage(value: number | undefined, total: number | undefined): string {
  if (!value || !total) {
    return '—'
  }
  return `${formatNumber((value / total) * 100, 1)}%`
}

export function StatisticsPage({ caseId, onBack, onOpenViewer }: StatisticsPageProps) {
  const [metrics, setMetrics] = useState<CaseMetricsResponse | null>(null)
  const [unit, setUnit] = useState<MetricUnit>('mm')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadMetrics() {
    setIsLoading(true)
    setError(null)
    try {
      setMetrics(await getCaseMetrics(caseId))
    } catch (loadError) {
      setMetrics(null)
      setError(apiMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadMetrics()
  }, [caseId])

  const maxVolume = useMemo(() => {
    if (!metrics) return 0
    return Math.max(...TISSUES.map((tissue) => convertVolume(metrics.volumes[tissue.volumeKey], unit) ?? 0))
  }, [metrics, unit])

  const maxSurface = useMemo(() => {
    if (!metrics) return 0
    return Math.max(...TISSUES.map((tissue) => convertSurface(metrics.surfaces[tissue.surfaceKey], unit) ?? 0))
  }, [metrics, unit])

  const volumeLabel = volumeUnitLabel(unit)
  const surfaceLabel = surfaceUnitLabel(unit)

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back to case</button>
          <p className="eyebrow">Case statistics</p>
          <h1>{metrics ? `${metrics.subject_id} · ${metrics.acquisition_date}` : `Case #${caseId}`}</h1>
          <p className="muted">Volume and surface-area metrics produced by mesh analysis.</p>
        </div>
        <div className="button-row">
          <div className="segmented-control compact-segmented" aria-label="Metric unit selector">
            <button type="button" className={unit === 'mm' ? 'active' : ''} onClick={() => setUnit('mm')}>mm</button>
            <button type="button" className={unit === 'cm' ? 'active' : ''} onClick={() => setUnit('cm')}>cm</button>
          </div>
          {onOpenViewer && <button type="button" className="secondary" onClick={onOpenViewer}>Open 3D view</button>}
          <button type="button" className="secondary" onClick={loadMetrics} disabled={isLoading}>Refresh</button>
        </div>
      </section>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Loading metrics...</p>}

      {metrics && (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <span>Total volume</span>
              <strong>{formatNumber(convertVolume(metrics.totals.volume_mm3, unit))} {volumeLabel}</strong>
              <p className="muted">{formatNumber(metrics.totals.volume_mm3 / 1000)} ml</p>
            </article>
            <article className="metric-card">
              <span>Total surface area</span>
              <strong>{formatNumber(convertSurface(metrics.totals.surface_mm2, unit))} {surfaceLabel}</strong>
            </article>
            <article className="metric-card">
              <span>Largest volume</span>
              <strong>{TISSUES.reduce((best, tissue) => ((metrics.volumes[tissue.volumeKey] ?? 0) > (metrics.volumes[best.volumeKey] ?? 0) ? tissue : best), TISSUES[0]).label}</strong>
            </article>
            <article className="metric-card">
              <span>Status</span>
              <strong>{metrics.status || 'none'}</strong>
            </article>
          </section>

          <section className="grid-two">
            <article className="card stack">
              <h2>Tissue volumes</h2>
              <div className="metric-bars">
                {TISSUES.map((tissue) => {
                  const rawValue = metrics.volumes[tissue.volumeKey] ?? 0
                  const value = convertVolume(rawValue, unit) ?? 0
                  const width = maxVolume > 0 ? Math.max(4, (value / maxVolume) * 100) : 0
                  return (
                    <div className="metric-bar-row" key={tissue.key}>
                      <div className="row-between"><span>{tissue.label}</span><strong>{formatNumber(value)} {volumeLabel}</strong></div>
                      <div className="metric-track"><span style={{ width: `${width}%` }} /></div>
                      <small>{formatNumber(rawValue / 1000)} ml · {percentage(rawValue, metrics.totals.volume_mm3)}</small>
                    </div>
                  )
                })}
              </div>
            </article>

            <article className="card stack">
              <h2>Tissue surface areas</h2>
              <div className="metric-bars">
                {TISSUES.map((tissue) => {
                  const rawValue = metrics.surfaces[tissue.surfaceKey] ?? 0
                  const value = convertSurface(rawValue, unit) ?? 0
                  const width = maxSurface > 0 ? Math.max(4, (value / maxSurface) * 100) : 0
                  return (
                    <div className="metric-bar-row" key={tissue.key}>
                      <div className="row-between"><span>{tissue.label}</span><strong>{formatNumber(value)} {surfaceLabel}</strong></div>
                      <div className="metric-track surface-track"><span style={{ width: `${width}%` }} /></div>
                    </div>
                  )
                })}
              </div>
            </article>
          </section>

          <section className="card stack">
            <h2>Metric table</h2>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>Tissue</th><th>Volume ({volumeLabel})</th><th>Volume (ml)</th><th>Volume share</th><th>Surface area ({surfaceLabel})</th></tr>
                </thead>
                <tbody>
                  {TISSUES.map((tissue) => {
                    const volume = metrics.volumes[tissue.volumeKey]
                    const surface = metrics.surfaces[tissue.surfaceKey]
                    return (
                      <tr key={tissue.key}>
                        <td>{tissue.label}</td>
                        <td>{formatNumber(convertVolume(volume, unit))}</td>
                        <td>{formatNumber(volume === undefined ? null : volume / 1000)}</td>
                        <td>{percentage(volume, metrics.totals.volume_mm3)}</td>
                        <td>{formatNumber(convertSurface(surface, unit))}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  )
}
