import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiMessage } from '../api/client'
import { getCaseMetrics } from '../api/metricsApi'
import { listSubjectCases, listSubjects } from '../api/subjectsApi'
import type { AuthorizedSubject, CaseMetricsResponse, MriCase, TissueKey } from '../types/api'

type StatisticsPageProps = {
  caseId?: number
  subjectId?: string
  onBack: () => void
  onOpenViewer?: (subjectId?: string, caseId?: number) => void
}

type MeasurementScale = 'mm' | 'cm'

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

function volumeValue(valueMm3: number | undefined, scale: MeasurementScale): number | null {
  if (valueMm3 === undefined) return null
  return scale === 'cm' ? valueMm3 / 1000 : valueMm3
}

function surfaceValue(valueMm2: number | undefined, scale: MeasurementScale): number | null {
  if (valueMm2 === undefined) return null
  return scale === 'cm' ? valueMm2 / 100 : valueMm2
}

function volumeUnit(scale: MeasurementScale): string {
  return scale === 'cm' ? 'cm³' : 'mm³'
}

function surfaceUnit(scale: MeasurementScale): string {
  return scale === 'cm' ? 'cm²' : 'mm²'
}

function cubicMmToMl(value: number | undefined): number | null {
  return value === undefined ? null : value / 1000
}

function percentage(value: number | undefined, total: number | undefined): string {
  if (!value || !total) return '—'
  return `${formatNumber((value / total) * 100, 1)}%`
}

export function StatisticsPage({ caseId, subjectId, onBack, onOpenViewer }: StatisticsPageProps) {
  const openedFromCase = Boolean(caseId && subjectId)
  const [subjects, setSubjects] = useState<AuthorizedSubject[]>([])
  const [subjectCases, setSubjectCases] = useState<MriCase[]>([])
  const [selectedSubjectId, setSelectedSubjectId] = useState(subjectId ?? '')
  const [selectedCaseId, setSelectedCaseId] = useState<number | ''>(caseId ?? '')
  const [metrics, setMetrics] = useState<CaseMetricsResponse | null>(null)
  const [measurementScale, setMeasurementScale] = useState<MeasurementScale>('mm')
  const [isLoadingSubjects, setIsLoadingSubjects] = useState(true)
  const [isLoadingCases, setIsLoadingCases] = useState(false)
  const [isLoadingMetrics, setIsLoadingMetrics] = useState(false)
  const [subjectTouched, setSubjectTouched] = useState(Boolean(subjectId))
  const [caseTouched, setCaseTouched] = useState(Boolean(caseId))
  const [hasCaseFieldBeenShown, setHasCaseFieldBeenShown] = useState(Boolean(subjectId))
  const [error, setError] = useState<string | null>(null)

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

  useEffect(() => {
    if (!selectedSubjectId) {
      setSubjectCases([])
      setSelectedCaseId('')
      return
    }
    let cancelled = false
    async function loadCases() {
      setIsLoadingCases(true)
      setError(null)
      try {
        const loaded = await listSubjectCases(selectedSubjectId)
        if (!cancelled) {
          setSubjectCases(loaded)
          setHasCaseFieldBeenShown(true)
        }
      } catch (loadError) {
        if (!cancelled) setError(apiMessage(loadError))
      } finally {
        if (!cancelled) setIsLoadingCases(false)
      }
    }
    loadCases()
    return () => { cancelled = true }
  }, [selectedSubjectId])

  const loadMetrics = useCallback(async () => {
    if (selectedCaseId === '') return
    setIsLoadingMetrics(true)
    setError(null)
    try {
      const loadedMetrics = await getCaseMetrics(Number(selectedCaseId))
      setMetrics(loadedMetrics)
    } catch (loadError) {
      setError(apiMessage(loadError))
    } finally {
      setIsLoadingMetrics(false)
    }
  }, [selectedCaseId])

  useEffect(() => {
    loadMetrics()
  }, [loadMetrics])

  const measurementReadyCases = subjectCases.filter((entry) => entry.capabilities?.can_view_metrics || entry.capabilities?.has_metrics)
  const showCaseField = Boolean(selectedSubjectId) && (hasCaseFieldBeenShown || !isLoadingCases)
  const hasMetrics = Boolean(metrics)
  const isChangingCase = hasMetrics && isLoadingMetrics
  const initialStatsStillLoading = openedFromCase && !hasMetrics && (isLoadingMetrics || isLoadingSubjects || isLoadingCases)
  const firstMetricsLoadInProgress = !initialStatsStillLoading && !hasMetrics && selectedCaseId !== ''

  const maxVolume = useMemo(() => {
    if (!metrics) return 0
    return Math.max(...TISSUES.map((tissue) => metrics.volumes[tissue.volumeKey] ?? 0))
  }, [metrics])

  const maxSurface = useMemo(() => {
    if (!metrics) return 0
    return Math.max(...TISSUES.map((tissue) => metrics.surfaces[tissue.surfaceKey] ?? 0))
  }, [metrics])

  function handleSubjectChange(nextSubjectId: string) {
    setSelectedSubjectId(nextSubjectId)
    setSelectedCaseId('')
    setSubjectTouched(true)
    setCaseTouched(false)
    if (nextSubjectId) setHasCaseFieldBeenShown(true)
  }

  function handleCaseChange(nextCaseId: string) {
    setSelectedCaseId(nextCaseId ? Number(nextCaseId) : '')
    setCaseTouched(Boolean(nextCaseId))
  }

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <button type="button" className="link-button" onClick={onBack}>← Back</button>
          <p className="eyebrow">Measurements</p>
          <h1>{metrics ? `${metrics.subject_id} · ${metrics.acquisition_date}` : 'Choose a scan'}</h1>
          <p className="muted">Review tissue volumes and surface areas for a completed scan.</p>
        </div>
        <div className="button-row">
          {onOpenViewer && selectedCaseId !== '' && <button type="button" className="secondary" onClick={() => onOpenViewer(selectedSubjectId || metrics?.subject_id, Number(selectedCaseId))}>Open 3D view</button>}
          <button type="button" className="secondary" onClick={loadMetrics} disabled={isLoadingMetrics || selectedCaseId === ''}>Refresh</button>
        </div>
      </section>

      {error && <p className="error-text">{error}</p>}

      {initialStatsStillLoading ? (
        <section className="card loading-card"><p className="muted">Loading statistics...</p></section>
      ) : (
        <section className="card form-grid choose-scan-card">
          <h2>Choose scan</h2>
          <label className={subjectTouched ? 'touched-field' : undefined}>
            Subject
            {isLoadingSubjects && <span className="muted small-note">Loading subjects...</span>}
            <select value={selectedSubjectId} disabled={isLoadingSubjects} onChange={(event) => handleSubjectChange(event.target.value)}>
              <option value="">Choose subject</option>
              {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.id} · {subject.case_count} cases</option>)}
            </select>
          </label>

          {selectedSubjectId && isLoadingCases && <p className="muted small-note">Loading cases...</p>}

          {showCaseField && (
            <label className={caseTouched ? 'touched-field' : undefined}>
              Case
              <select value={selectedCaseId} disabled={!selectedSubjectId || isLoadingCases} onChange={(event) => handleCaseChange(event.target.value)}>
                <option value="">Choose completed scan</option>
                {measurementReadyCases.map((entry) => <option key={entry.id} value={entry.id}>{entry.acquisition_date}</option>)}
              </select>
            </label>
          )}

          {showCaseField && (
            <label>
              Measurement scale
              <select value={measurementScale} onChange={(event) => setMeasurementScale(event.target.value as MeasurementScale)}>
                <option value="mm">Millimetres</option>
                <option value="cm">Centimetres</option>
              </select>
            </label>
          )}
        </section>
      )}

      {isChangingCase && <section className="card loading-card"><p className="muted">Loading for new case...</p></section>}
      {firstMetricsLoadInProgress && <section className="card loading-card"><p className="muted">Loading statistics...</p></section>}

      {metrics && (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <span>Total volume</span>
              <strong>{formatNumber(volumeValue(metrics.totals.volume_mm3, measurementScale))} {volumeUnit(measurementScale)}</strong>
              <p className="muted">{formatNumber(metrics.totals.volume_mm3 / 1000)} ml</p>
            </article>
            <article className="metric-card">
              <span>Total surface area</span>
              <strong>{formatNumber(surfaceValue(metrics.totals.surface_mm2, measurementScale))} {surfaceUnit(measurementScale)}</strong>
            </article>
            <article className="metric-card">
              <span>Largest volume</span>
              <strong>{TISSUES.reduce((best, tissue) => ((metrics.volumes[tissue.volumeKey] ?? 0) > (metrics.volumes[best.volumeKey] ?? 0) ? tissue : best), TISSUES[0]).label}</strong>
            </article>
            <article className="metric-card">
              <span>Subject</span>
              <strong>{metrics.subject_id}</strong>
            </article>
          </section>

          <section className="grid-two">
            <article className="card stack">
              <h2>Tissue volumes</h2>
              <div className="metric-bars">
                {TISSUES.map((tissue) => {
                  const value = metrics.volumes[tissue.volumeKey] ?? 0
                  const width = maxVolume > 0 ? Math.max(4, (value / maxVolume) * 100) : 0
                  return (
                    <div className="metric-bar-row" key={tissue.key}>
                      <div className="row-between"><span>{tissue.label}</span><strong>{formatNumber(volumeValue(value, measurementScale))} {volumeUnit(measurementScale)}</strong></div>
                      <div className="metric-track"><span style={{ width: `${width}%` }} /></div>
                      <small>{formatNumber(cubicMmToMl(value))} ml · {percentage(value, metrics.totals.volume_mm3)}</small>
                    </div>
                  )
                })}
              </div>
            </article>

            <article className="card stack">
              <h2>Tissue surface areas</h2>
              <div className="metric-bars">
                {TISSUES.map((tissue) => {
                  const value = metrics.surfaces[tissue.surfaceKey] ?? 0
                  const width = maxSurface > 0 ? Math.max(4, (value / maxSurface) * 100) : 0
                  return (
                    <div className="metric-bar-row" key={tissue.key}>
                      <div className="row-between"><span>{tissue.label}</span><strong>{formatNumber(surfaceValue(value, measurementScale))} {surfaceUnit(measurementScale)}</strong></div>
                      <div className="metric-track surface-track"><span style={{ width: `${width}%` }} /></div>
                    </div>
                  )
                })}
              </div>
            </article>
          </section>

          <section className="card stack">
            <h2>Measurement table</h2>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>Tissue</th><th>Volume ({volumeUnit(measurementScale)})</th><th>Volume (ml)</th><th>Volume share</th><th>Surface area ({surfaceUnit(measurementScale)})</th></tr>
                </thead>
                <tbody>
                  {TISSUES.map((tissue) => {
                    const volume = metrics.volumes[tissue.volumeKey]
                    const surface = metrics.surfaces[tissue.surfaceKey]
                    return (
                      <tr key={tissue.key}>
                        <td>{tissue.label}</td>
                        <td>{formatNumber(volumeValue(volume, measurementScale))}</td>
                        <td>{formatNumber(cubicMmToMl(volume))}</td>
                        <td>{percentage(volume, metrics.totals.volume_mm3)}</td>
                        <td>{formatNumber(surfaceValue(surface, measurementScale))}</td>
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
