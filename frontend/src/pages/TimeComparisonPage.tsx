import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiMessage } from '../api/client'
import { createEvolutionVisualComparisonObjectUrl, getEvolutionReport, listEvolutionDates } from '../api/metricsApi'
import { Modal } from '../components/Modal'
import type { EvolutionComparisonMethod } from '../api/metricsApi'
import { listSubjects } from '../api/subjectsApi'
import type { AuthorizedSubject, EvolutionDateEntry, EvolutionReport, TissueKey } from '../types/api'
import { formatNumber, metricUnit as measurementUnit, scaleMetricValue } from '../utils/measurements'
import type { MeasurementScale, MetricDimension } from '../utils/measurements'

const Comparison3DViewer = lazy(() => import('../components/Comparison3DViewer').then((module) => ({ default: module.Comparison3DViewer })))

type TimeComparisonPageProps = {
  subjectId?: string
  onBack: () => void
}

type MetricGroup = 'volumes_mm3' | 'surfaces_mm2'

const TISSUES: Array<{ key: TissueKey; label: string }> = [
  { key: 'csf', label: 'CSF' },
  { key: 'gm', label: 'Gray matter' },
  { key: 'wm', label: 'White matter' },
]

function metricLabel(group: MetricGroup): string {
  return group === 'volumes_mm3' ? 'Volume' : 'Surface area'
}

function metricDimension(group: MetricGroup): MetricDimension {
  return group === 'volumes_mm3' ? 'volume' : 'surface'
}

function metricUnit(group: MetricGroup, scale: MeasurementScale): string {
  return measurementUnit(metricDimension(group), scale)
}

function tissueLabel(tissue: TissueKey): string {
  return TISSUES.find((entry) => entry.key === tissue)?.label ?? tissue.toUpperCase()
}

function ComparisonLineChart({ report, metricGroup, tissue, scale }: { report: EvolutionReport; metricGroup: MetricGroup; tissue: TissueKey; scale: MeasurementScale }) {
  const values = report.points.map((point) => scaleMetricValue(point[metricGroup][tissue].value, metricDimension(metricGroup), scale) ?? 0)
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
  const [changedRegionObjectUrl, setChangedRegionObjectUrl] = useState<string | null>(null)
  const [lastVisualSignature, setLastVisualSignature] = useState<string | null>(null)
  const [isLoadingVisual, setIsLoadingVisual] = useState(false)
  const [visualError, setVisualError] = useState<string | null>(null)
  const [changedRegionError, setChangedRegionError] = useState<string | null>(null)
  const [comparisonHelpOpen, setComparisonHelpOpen] = useState(false)
  const visualObjectUrlRef = useRef<string | null>(null)
  const changedRegionObjectUrlRef = useRef<string | null>(null)

  const clearVisualObjectUrls = useCallback(() => {
    if (visualObjectUrlRef.current) {
      URL.revokeObjectURL(visualObjectUrlRef.current)
      visualObjectUrlRef.current = null
    }
    if (changedRegionObjectUrlRef.current) {
      URL.revokeObjectURL(changedRegionObjectUrlRef.current)
      changedRegionObjectUrlRef.current = null
    }
  }, [])

  const resetVisualComparison = useCallback(() => {
    setVisualOpen(false)
    setVisualObjectUrl(null)
    setChangedRegionObjectUrl(null)
    setLastVisualSignature(null)
    setVisualError(null)
    setChangedRegionError(null)
    clearVisualObjectUrls()
  }, [clearVisualObjectUrls])

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

  useEffect(() => () => clearVisualObjectUrls(), [clearVisualObjectUrls])

  const readyDates = useMemo(() => dateEntries.filter((entry) => entry.ready_for_json), [dateEntries])
  const visualRequestSignature = useMemo(() => {
    if (!report || !selectedSubjectId) return null
    const sensitivity = comparisonMethod === 'pve' ? pveThreshold : distanceThresholdMm
    return [selectedSubjectId, report.start_date, report.end_date, selectedTissue, comparisonMethod, sensitivity].join('|')
  }, [comparisonMethod, distanceThresholdMm, pveThreshold, report, selectedSubjectId, selectedTissue])
  const visualNeedsRefresh = Boolean(visualOpen && visualRequestSignature && visualRequestSignature !== lastVisualSignature)
  const canOpenVisualComparison = Boolean(report) && !isLoadingVisual && (!visualOpen || visualNeedsRefresh)

  async function buildReport() {
    if (!selectedSubjectId || !startDate || !endDate) {
      setError('Select a subject, start date and end date first.')
      return
    }
    setIsLoadingReport(true)
    setError(null)
    try {
      setReport(await getEvolutionReport(selectedSubjectId, startDate, endDate))
      resetVisualComparison()
    } catch (loadError) {
      setReport(null)
      resetVisualComparison()
      setError(apiMessage(loadError))
    } finally {
      setIsLoadingReport(false)
    }
  }

  const loadVisualComparison = useCallback(async () => {
    if (!report || !selectedSubjectId || !visualRequestSignature) return
    setIsLoadingVisual(true)
    setVisualError(null)
    setChangedRegionError(null)

    let comparisonUrl: string | null = null
    let changedRegionUrl: string | null = null
    let comparisonLoadError: string | null = null
    let changedRegionLoadError: string | null = null

    try {
      comparisonUrl = await createEvolutionVisualComparisonObjectUrl({
        subjectId: selectedSubjectId,
        startDate: report.start_date,
        endDate: report.end_date,
        targetDate: report.end_date,
        tissue: selectedTissue,
        comparisonMethod,
        visualMode: 'changed_unchanged',
        pveThreshold,
        distanceThresholdMm,
      })
    } catch (loadError) {
      comparisonLoadError = apiMessage(loadError)
    }

    try {
      changedRegionUrl = await createEvolutionVisualComparisonObjectUrl({
        subjectId: selectedSubjectId,
        startDate: report.start_date,
        endDate: report.end_date,
        targetDate: report.end_date,
        tissue: selectedTissue,
        comparisonMethod,
        visualMode: 'changed_region_before_after',
        pveThreshold,
        distanceThresholdMm,
      })
    } catch (loadError) {
      changedRegionLoadError = apiMessage(loadError)
    }

    clearVisualObjectUrls()
    visualObjectUrlRef.current = comparisonUrl
    changedRegionObjectUrlRef.current = changedRegionUrl
    setVisualObjectUrl(comparisonUrl)
    setChangedRegionObjectUrl(changedRegionUrl)
    setVisualError(comparisonLoadError)
    setChangedRegionError(changedRegionLoadError)
    setLastVisualSignature(comparisonUrl || changedRegionUrl ? visualRequestSignature : null)
    setIsLoadingVisual(false)
  }, [clearVisualObjectUrls, report, selectedTissue, selectedSubjectId, comparisonMethod, pveThreshold, distanceThresholdMm, visualRequestSignature])

  function handleOpenVisualComparison() {
    if (!report || !canOpenVisualComparison) return
    setVisualOpen(true)
    void loadVisualComparison()
  }

  function handleSubjectChange(value: string) {
    setSelectedSubjectId(value)
    setDateEntries([])
    setStartDate('')
    setEndDate('')
    setReport(null)
    resetVisualComparison()
  }

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back</button>
          <p className="eyebrow">Compare over time</p>
          <h1>{selectedSubjectId || 'Choose a subject'}</h1>
          <p className="muted">Compare tissue measurements between acquisition dates for one subject.</p>
        </div>
        <button type="button" className="secondary" onClick={loadDates} disabled={isLoadingDates || !selectedSubjectId}>Refresh dates</button>
      </section>

      {error && <p className="error-text">{error}</p>}

      <section className="card form-grid">
        <h2>Choose subject</h2>
        <label>
          Subject
          {isLoadingSubjects && <span className="muted small-note">Loading subjects...</span>}
          {!isLoadingSubjects && subjects.length > 0 && <span className="muted small-note">Subjects loaded. Choose one to continue.</span>}
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
          <h2>Available dates</h2>
          {isLoadingDates && <p className="muted">Loading dates...</p>}
          {!isLoadingDates && selectedSubjectId && readyDates.length < 2 && (
            <p className="muted">At least two completed scans are required for comparison.</p>
          )}
          {!selectedSubjectId && <p className="muted">Choose a subject to load available acquisition dates.</p>}
          <div className="date-chip-grid">
            {dateEntries.map((entry) => (
              <span className={`date-chip ${entry.ready_for_json ? 'ready' : ''}`} key={entry.case_id}>
                <strong>{entry.acquisition_date}</strong>
                <small>{entry.ready_for_json ? 'ready' : 'not ready'}</small>
              </span>
            ))}
          </div>
        </article>

        <form className="card form-grid" onSubmit={(event) => { event.preventDefault(); buildReport() }}>
          <h2>Compare dates</h2>
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
          <button type="submit" disabled={readyDates.length < 2 || isLoadingReport}>{isLoadingReport ? 'Comparing...' : 'Compare dates'}</button>
        </form>
      </section>

      {report && (
        <>
          <section className="card stack">
            <div className="row-between">
              <div>
                <h2>Measurement evolution</h2>
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
                  3D comparison
                  <select value={comparisonMethod} onChange={(event) => setComparisonMethod(event.target.value as EvolutionComparisonMethod)}>
                    <option value="nearest_distance">Surface distance</option>
                    <option value="pve">Tissue probability</option>
                  </select>
                </label>
                {comparisonMethod === 'pve' ? (
                  <label className="inline-field">
                    Sensitivity
                    <input type="number" min="0" step="0.05" max="1" value={pveThreshold} onChange={(event) => setPveThreshold(Number(event.target.value))} />
                    <span className="muted small-note">change threshold</span>
                  </label>
                ) : (
                  <label className="inline-field">
                    Sensitivity
                    <input type="number" min="0" step="0.25" value={distanceThresholdMm} onChange={(event) => setDistanceThresholdMm(Number(event.target.value))} />
                    <span className="muted small-note">mm</span>
                  </label>
                )}
                <button type="button" className="secondary" onClick={handleOpenVisualComparison} disabled={!canOpenVisualComparison}>
                  {isLoadingVisual ? 'Building...' : visualOpen ? 'Update visual comparison' : 'Open visual comparison'}
                </button>
                <button
                  type="button"
                  className="help-icon-button"
                  onClick={() => setComparisonHelpOpen(true)}
                  aria-label="Explain visual comparison methods"
                  title="Explain visual comparison methods"
                >
                  ?
                </button>
              </div>
            </div>
            <ComparisonLineChart report={report} metricGroup={metricGroup} tissue={selectedTissue} scale={measurementScale} />
            {visualOpen && (
              <p className="muted small-note">
                Change the sensitivity, tissue or comparison method, then use Update visual comparison to rebuild the 3D view. Current tissue: {tissueLabel(selectedTissue)}. 3D comparison: {comparisonMethod === 'pve' ? 'tissue probability' : 'surface distance'}.
              </p>
            )}
          </section>

          <section className="card stack">
            <h2>Comparison table</h2>
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
                        <td>{formatNumber(scaleMetricValue(metric.value, metricDimension(metricGroup), measurementScale))}</td>
                        <td>{formatNumber(scaleMetricValue(metric.absolute_change_from_baseline, metricDimension(metricGroup), measurementScale))} ({formatNumber(metric.change_from_baseline_percent, 2)}%)</td>
                        <td>{metric.previous_value === null ? '—' : `${formatNumber(scaleMetricValue(metric.absolute_change_from_previous ?? 0, metricDimension(metricGroup), measurementScale))} (${formatNumber(metric.change_from_previous_percent, 2)}%)`}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>


          {visualOpen && (
            <Suspense fallback={<section className="card"><p className="muted">Loading visual comparison...</p></section>}>
              <Comparison3DViewer
                objectUrl={visualObjectUrl}
                title="Visual comparison"
                subtitle={comparisonMethod === 'pve'
                  ? `Shows unchanged versus changed ${tissueLabel(selectedTissue)} areas using tissue-probability differences. Sensitivity: ${pveThreshold}.`
                  : `Shows unchanged versus changed ${tissueLabel(selectedTissue)} surface areas using a ${distanceThresholdMm} mm distance threshold.`}
                loadingText="Building visual comparison..."
                isLoading={isLoadingVisual}
                error={visualError}
              />

              <Comparison3DViewer
                objectUrl={changedRegionObjectUrl}
                title="Changed region before / after"
                subtitle={comparisonMethod === 'pve'
                  ? `Shows only the detected changed ${tissueLabel(selectedTissue)} region, once from ${report.baseline_date} and once from ${report.end_date}.`
                  : `Shows only the ${tissueLabel(selectedTissue)} surface parts that moved more than ${distanceThresholdMm} mm, before and after.`}
                loadingText="Building changed-region before/after view..."
                isLoading={isLoadingVisual}
                error={changedRegionError}
                variant="beforeAfter"
                layerLabels={{ unchanged: 'Before region', changed: 'After region' }}
              />
            </Suspense>
          )}
        </>
      )}

      {comparisonHelpOpen && (
        <Modal title="How visual comparison works" eyebrow="Comparison help" onClose={() => setComparisonHelpOpen(false)}>
          <div className="stack comparison-help-content">
            <p>
              Visual comparison highlights the selected tissue between the baseline scan and the target scan.
              Unchanged areas use the baseline color, while detected changes use the change color.
              The changed-region before/after view then uses the same detected-change mask to show only that region in the baseline scan and in the target scan.
            </p>
            <article>
              <h3>Tissue probability</h3>
              <p className="muted">
                This method compares the FAST tissue-probability maps after they are aligned to the same template space.
                Sensitivity is the minimum probability difference needed for a point to be marked as changed.
                Lower values show subtler changes; higher values keep only stronger changes.
              </p>
            </article>
            <article>
              <h3>Surface distance</h3>
              <p className="muted">
                This method compares the distance between the generated tissue surfaces. Sensitivity is measured in millimetres.
                A lower distance marks smaller shape differences as changed; a higher distance shows only larger surface shifts.
              </p>
            </article>
          </div>
        </Modal>
      )}
    </main>
  )
}
