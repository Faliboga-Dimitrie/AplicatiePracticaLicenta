import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiMessage } from '../api/client'
import { createEvolutionVisualComparisonObjectUrl, getEvolutionReport, listEvolutionDates } from '../api/metricsApi'
import type { EvolutionComparisonMethod } from '../api/metricsApi'
import { listSubjects } from '../api/subjectsApi'
import { Comparison3DViewer } from '../components/Comparison3DViewer'
import type { AuthorizedSubject, EvolutionDateEntry, EvolutionReport, TissueKey } from '../types/api'

type TimeComparisonPageProps = {
  subjectId?: string
  onBack: () => void
}

type MetricGroup = 'volumes_mm3' | 'surfaces_mm2'
type MeasurementScale = 'mm' | 'cm'

const TISSUES: Array<{ key: TissueKey; label: string }> = [
  { key: 'csf', label: 'CSF' },
  { key: 'gm', label: 'Gray matter' },
  { key: 'wm', label: 'White matter' },
]

function formatNumber(value: number | null | undefined, fractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: fractionDigits }).format(value)
}

function metricLabel(group: MetricGroup): string {
  return group === 'volumes_mm3' ? 'Volume' : 'Surface area'
}

function convertMetricValue(value: number, group: MetricGroup, scale: MeasurementScale): number {
  if (scale === 'mm') return value
  return group === 'volumes_mm3' ? value / 1000 : value / 100
}

function metricUnit(group: MetricGroup, scale: MeasurementScale): string {
  if (group === 'volumes_mm3') return scale === 'cm' ? 'cm³' : 'mm³'
  return scale === 'cm' ? 'cm²' : 'mm²'
}

function tissueLabel(tissue: TissueKey): string {
  return TISSUES.find((entry) => entry.key === tissue)?.label ?? tissue.toUpperCase()
}

function ComparisonLineChart({ report, metricGroup, tissue, scale }: { report: EvolutionReport; metricGroup: MetricGroup; tissue: TissueKey; scale: MeasurementScale }) {
  const values = report.points.map((point) => convertMetricValue(point[metricGroup][tissue].value, metricGroup, scale))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const width = 720
  const height = 240
  const padding = 34
  const points = values.map((value, index) => {
    const x = padding + (index / Math.max(1, values.length - 1)) * (width - padding * 2)
    const y = height - padding - ((value - min) / range) * (height - padding * 2)
    return { x, y, value, date: report.points[index].acquisition_date }
  })
  const polyline = points.map((point) => `${point.x},${point.y}`).join(' ')

  return (
    <div className="chart-card">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${metricLabel(metricGroup)} over time`}>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} className="chart-axis" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} className="chart-axis" />
        <polyline points={polyline} className="chart-line" fill="none" />
        {points.map((point) => (
          <g key={point.date}>
            <circle cx={point.x} cy={point.y} r="5" className="chart-dot" />
            <text x={point.x} y={height - 10} textAnchor="middle" className="chart-label">{point.date.slice(5)}</text>
            <text x={point.x} y={point.y - 12} textAnchor="middle" className="chart-value">{formatNumber(point.value, 0)}</text>
          </g>
        ))}
      </svg>
      <p className="muted small-note">Y-axis is auto-scaled for the selected tissue and metric. Unit: {metricUnit(metricGroup, scale)}.</p>
    </div>
  )
}

export function TimeComparisonPage({ subjectId, onBack }: TimeComparisonPageProps) {
  const [subjects, setSubjects] = useState<AuthorizedSubject[]>([])
  const [selectedSubjectId, setSelectedSubjectId] = useState(subjectId ?? '')
  const [dateEntries, setDateEntries] = useState<EvolutionDateEntry[]>([])
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [report, setReport] = useState<EvolutionReport | null>(null)
  const [metricGroup, setMetricGroup] = useState<MetricGroup>('volumes_mm3')
  const [measurementScale, setMeasurementScale] = useState<MeasurementScale>('mm')
  const [selectedTissue, setSelectedTissue] = useState<TissueKey>('gm')
  const [comparisonMethod, setComparisonMethod] = useState<EvolutionComparisonMethod>('pve')
  const [pveThreshold, setPveThreshold] = useState(0.2)
  const [distanceThresholdMm, setDistanceThresholdMm] = useState(1)
  const [isLoadingSubjects, setIsLoadingSubjects] = useState(true)
  const [isLoadingDates, setIsLoadingDates] = useState(false)
  const [isLoadingReport, setIsLoadingReport] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [visualOpen, setVisualOpen] = useState(false)
  const [visualObjectUrl, setVisualObjectUrl] = useState<string | null>(null)
  const [isLoadingVisual, setIsLoadingVisual] = useState(false)
  const [visualError, setVisualError] = useState<string | null>(null)
  const visualObjectUrlRef = useRef<string | null>(null)

  const clearVisualObjectUrl = useCallback(() => {
    if (visualObjectUrlRef.current) {
      URL.revokeObjectURL(visualObjectUrlRef.current)
      visualObjectUrlRef.current = null
    }
  }, [])

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

  const loadDates = useCallback(async () => {
    if (!selectedSubjectId) {
      setDateEntries([])
      return
    }
    setIsLoadingDates(true)
    setError(null)
    try {
      const response = await listEvolutionDates(selectedSubjectId)
      setDateEntries(response.dates)
      const readyDates = response.dates.filter((entry) => entry.ready_for_json).map((entry) => entry.acquisition_date)
      setStartDate((current) => current && readyDates.includes(current) ? current : readyDates[0] || '')
      setEndDate((current) => current && readyDates.includes(current) ? current : readyDates[readyDates.length - 1] || '')
    } catch (loadError) {
      setDateEntries([])
      setError(apiMessage(loadError))
    } finally {
      setIsLoadingDates(false)
    }
  }, [selectedSubjectId])

  useEffect(() => {
    loadDates()
  }, [loadDates])

  useEffect(() => () => clearVisualObjectUrl(), [clearVisualObjectUrl])

  const readyDates = useMemo(() => dateEntries.filter((entry) => entry.ready_for_json), [dateEntries])

  async function buildReport() {
    if (!selectedSubjectId || !startDate || !endDate) {
      setError('Select a subject, start date and end date first.')
      return
    }
    setIsLoadingReport(true)
    setError(null)
    try {
      setReport(await getEvolutionReport(selectedSubjectId, startDate, endDate))
    } catch (loadError) {
      setReport(null)
      setVisualOpen(false)
      setVisualObjectUrl(null)
      clearVisualObjectUrl()
      setError(apiMessage(loadError))
    } finally {
      setIsLoadingReport(false)
    }
  }

  const loadVisualComparison = useCallback(async () => {
    if (!report || !selectedSubjectId) return
    setIsLoadingVisual(true)
    setVisualError(null)
    try {
      const objectUrl = await createEvolutionVisualComparisonObjectUrl({
        subjectId: selectedSubjectId,
        startDate: report.start_date,
        endDate: report.end_date,
        targetDate: report.end_date,
        tissue: selectedTissue,
        comparisonMethod,
        pveThreshold,
        distanceThresholdMm,
      })
      clearVisualObjectUrl()
      visualObjectUrlRef.current = objectUrl
      setVisualObjectUrl(objectUrl)
    } catch (loadError) {
      setVisualObjectUrl(null)
      clearVisualObjectUrl()
      setVisualError(apiMessage(loadError))
    } finally {
      setIsLoadingVisual(false)
    }
  }, [clearVisualObjectUrl, report, selectedTissue, selectedSubjectId, comparisonMethod, pveThreshold, distanceThresholdMm])

  useEffect(() => {
    if (visualOpen && report) loadVisualComparison()
  }, [loadVisualComparison, report, visualOpen])

  function handleOpenVisualComparison() {
    if (!report) return
    if (visualOpen) loadVisualComparison()
    else setVisualOpen(true)
  }

  function handleSubjectChange(value: string) {
    setSelectedSubjectId(value)
    setDateEntries([])
    setStartDate('')
    setEndDate('')
    setReport(null)
    setVisualOpen(false)
    setVisualObjectUrl(null)
    clearVisualObjectUrl()
  }

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back</button>
          <p className="eyebrow">Time comparison</p>
          <h1>{selectedSubjectId || 'Choose a subject'}</h1>
          <p className="muted">Compare volume and surface metrics between multiple acquisition dates.</p>
        </div>
        <button type="button" className="secondary" onClick={loadDates} disabled={isLoadingDates || !selectedSubjectId}>Refresh dates</button>
      </section>

      {error && <p className="error-text">{error}</p>}

      <section className="card form-grid">
        <h2>Choose subject and scale</h2>
        <label>
          Subject
          <select value={selectedSubjectId} disabled={isLoadingSubjects} onChange={(event) => handleSubjectChange(event.target.value)}>
            <option value="">Choose subject</option>
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.id} · {subject.case_count} cases</option>)}
          </select>
        </label>
        <label>
          Measurement scale
          <select value={measurementScale} onChange={(event) => setMeasurementScale(event.target.value as MeasurementScale)}>
            <option value="mm">Millimetres</option>
            <option value="cm">Centimetres</option>
          </select>
        </label>
      </section>

      <section className="grid-two">
        <article className="card stack">
          <h2>Metric-ready dates</h2>
          {isLoadingDates && <p className="muted">Loading dates...</p>}
          {!isLoadingDates && selectedSubjectId && readyDates.length < 2 && (
            <p className="muted">At least two cases with mesh-analysis metrics are required for time comparison.</p>
          )}
          {!selectedSubjectId && <p className="muted">Choose a subject to load available acquisition dates.</p>}
          <div className="date-chip-grid">
            {dateEntries.map((entry) => (
              <span className={`date-chip ${entry.ready_for_json ? 'ready' : ''}`} key={entry.case_id}>
                <strong>{entry.acquisition_date}</strong>
                <small>{entry.ready_for_json ? 'metrics ready' : 'no metrics'}</small>
              </span>
            ))}
          </div>
        </article>

        <form className="card form-grid" onSubmit={(event) => { event.preventDefault(); buildReport() }}>
          <h2>Build comparison</h2>
          <label>
            Start date
            <select value={startDate} onChange={(event) => setStartDate(event.target.value)}>
              <option value="">Choose start</option>
              {readyDates.map((entry) => <option value={entry.acquisition_date} key={entry.case_id}>{entry.acquisition_date}</option>)}
            </select>
          </label>
          <label>
            End date
            <select value={endDate} onChange={(event) => setEndDate(event.target.value)}>
              <option value="">Choose end</option>
              {readyDates.map((entry) => <option value={entry.acquisition_date} key={entry.case_id}>{entry.acquisition_date}</option>)}
            </select>
          </label>
          <button type="submit" disabled={readyDates.length < 2 || isLoadingReport}>{isLoadingReport ? 'Building...' : 'Build report'}</button>
        </form>
      </section>

      {report && (
        <>
          <section className="card stack">
            <div className="row-between">
              <div>
                <h2>Evolution report</h2>
                <p className="muted">Baseline: {report.baseline_date}. Interval: {report.start_date} → {report.end_date}.</p>
              </div>
              <div className="button-row">
                <select value={metricGroup} onChange={(event) => setMetricGroup(event.target.value as MetricGroup)}>
                  <option value="volumes_mm3">Volumes</option>
                  <option value="surfaces_mm2">Surfaces</option>
                </select>
                <select value={selectedTissue} onChange={(event) => setSelectedTissue(event.target.value as TissueKey)}>
                  {TISSUES.map((tissue) => <option key={tissue.key} value={tissue.key}>{tissue.label}</option>)}
                </select>
                <label className="inline-field">
                  Method
                  <select value={comparisonMethod} onChange={(event) => setComparisonMethod(event.target.value as EvolutionComparisonMethod)}>
                    <option value="nearest_distance">Nearest distance · fast / less precise</option>
                    <option value="pve">PVE comparison · slower / more precise</option>
                  </select>
                </label>
                {comparisonMethod === 'pve' ? (
                  <label className="inline-field">
                    PVE threshold
                    <input type="number" min="0" step="0.05" max="1" value={pveThreshold} onChange={(event) => setPveThreshold(Number(event.target.value))} />
                    <span className="muted small-note">probability Δ</span>
                  </label>
                ) : (
                  <label className="inline-field">
                    Distance threshold
                    <input type="number" min="0" step="0.25" value={distanceThresholdMm} onChange={(event) => setDistanceThresholdMm(Number(event.target.value))} />
                    <span className="muted small-note">mm</span>
                  </label>
                )}
                <button type="button" className="secondary" onClick={handleOpenVisualComparison} disabled={isLoadingVisual}>
                  {visualOpen ? 'Reload 3D comparison' : 'Open 3D comparison'}
                </button>
              </div>
            </div>
            <ComparisonLineChart report={report} metricGroup={metricGroup} tissue={selectedTissue} scale={measurementScale} />
            {visualOpen && (
              <p className="muted small-note">
                The 3D comparison is rebuilt automatically when the selected tissue, method, or threshold changes. Current tissue: {tissueLabel(selectedTissue)}. Method: {comparisonMethod === 'pve' ? 'PVE comparison' : 'nearest-distance comparison'}.
              </p>
            )}
          </section>

          {visualOpen && (
            <Comparison3DViewer
              objectUrl={visualObjectUrl}
              title="3D visual comparison"
              subtitle={comparisonMethod === 'pve'
                ? `PVE comparison for ${tissueLabel(selectedTissue)}. The GLB contains two layers: unchanged and changed. If tissue volume increased, the target mesh is used as reference; otherwise the baseline mesh is used. PVE threshold: ${pveThreshold}.`
                : `Nearest-distance comparison for ${tissueLabel(selectedTissue)}. The GLB contains two layers: unchanged and changed. If tissue volume increased, the target mesh is used as reference; otherwise the baseline mesh is used. Distance threshold: ${distanceThresholdMm} mm.`}
              loadingText="Building comparison GLB..."
              isLoading={isLoadingVisual}
              error={visualError}
              onReload={loadVisualComparison}
            />
          )}

          <section className="card stack">
            <h2>Point-by-point comparison</h2>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>{metricLabel(metricGroup)} ({metricUnit(metricGroup, measurementScale)})</th>
                    <th>Change vs baseline</th>
                    <th>Change vs previous</th>
                  </tr>
                </thead>
                <tbody>
                  {report.points.map((point) => {
                    const metric = point[metricGroup][selectedTissue]
                    return (
                      <tr key={point.acquisition_date}>
                        <td>{point.acquisition_date}{point.is_baseline ? ' · baseline' : ''}</td>
                        <td>{formatNumber(convertMetricValue(metric.value, metricGroup, measurementScale))}</td>
                        <td>{formatNumber(convertMetricValue(metric.absolute_change_from_baseline, metricGroup, measurementScale))} ({formatNumber(metric.change_from_baseline_percent, 2)}%)</td>
                        <td>{metric.previous_value === null ? '—' : `${formatNumber(convertMetricValue(metric.absolute_change_from_previous ?? 0, metricGroup, measurementScale))} (${formatNumber(metric.change_from_previous_percent, 2)}%)`}</td>
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
