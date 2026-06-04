export type MeasurementScale = 'mm' | 'cm'
export type MetricDimension = 'volume' | 'surface'

export function formatNumber(value: number | null | undefined, fractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: fractionDigits }).format(value)
}

export function scaleMetricValue(
  value: number | null | undefined,
  dimension: MetricDimension,
  scale: MeasurementScale,
): number | null {
  if (value === null || value === undefined) return null
  if (scale === 'mm') return value
  return dimension === 'volume' ? value / 1000 : value / 100
}

export function metricUnit(dimension: MetricDimension, scale: MeasurementScale): string {
  if (dimension === 'volume') return scale === 'cm' ? 'cm³' : 'mm³'
  return scale === 'cm' ? 'cm²' : 'mm²'
}

export function cubicMmToMl(valueMm3: number | null | undefined): number | null {
  return valueMm3 === null || valueMm3 === undefined ? null : valueMm3 / 1000
}

export function percentage(value: number | null | undefined, total: number | null | undefined): string {
  if (!value || !total) return '—'
  return `${formatNumber((value / total) * 100, 1)}%`
}
