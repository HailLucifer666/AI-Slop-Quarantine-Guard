/**
 * Pure trend helpers for KPI sparklines + delta arrows. Real data only:
 * scans with no `created_at` (unorderable) or no analytics are excluded, and
 * `delta` is null with fewer than 2 points so the UI renders "—" instead of a
 * misleading 0.
 */
import type { ScanSummary } from "./types"

export type TrendKey = "findings" | "certain" | "clean" | "duration"

export interface Trend {
  series: number[]
  delta: number | null
}

function metric(s: ScanSummary, key: TrendKey): number {
  const a = s.analytics
  switch (key) {
    case "findings":
      return a?.total_findings ?? 0
    case "certain":
      return a?.by_confidence?.CERTAIN ?? 0
    case "clean":
      return a?.clean ? 100 : 0
    case "duration":
      return s.duration_ms ?? 0
  }
}

/**
 * Oldest→newest series of `key` across completed, time-stamped scans (last
 * `window` points). `delta` = last minus previous point, or null if <2 points.
 */
export function computeTrend(scans: ScanSummary[], key: TrendKey, window = 10): Trend {
  const ordered = scans
    .filter((s) => s.status === "completed" && s.created_at && s.analytics)
    .sort((a, b) => (a.created_at! < b.created_at! ? -1 : 1))

  const series = ordered.map((s) => metric(s, key)).slice(-window)
  const delta = series.length >= 2 ? series[series.length - 1] - series[series.length - 2] : null
  return { series, delta }
}
