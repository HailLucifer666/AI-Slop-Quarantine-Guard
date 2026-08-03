/** Roll up many scans into the Overview's headline numbers (client-side). */
import type { ScanSummary } from "./types"

export interface Overview {
  scanned: number
  completed: number
  cleanRate: number // 0–100, of completed scans
  certainTotal: number
  findingsTotal: number
  avgMs: number | null
  byRule: Record<string, number> // SQG001..006 -> count
  topFiles: { file_path: string; count: number }[]
}

export function aggregateScans(scans: ScanSummary[]): Overview {
  const completed = scans.filter((s) => s.status === "completed")
  const clean = completed.filter((s) => s.analytics?.clean)
  const byRule: Record<string, number> = {}
  const fileCounts: Record<string, number> = {}
  let certainTotal = 0
  let findingsTotal = 0
  let msSum = 0
  let msCount = 0

  for (const s of completed) {
    const a = s.analytics
    if (!a) continue
    findingsTotal += a.total_findings
    certainTotal += a.by_confidence?.CERTAIN ?? 0
    for (const [rule, n] of Object.entries(a.by_rule ?? {})) byRule[rule] = (byRule[rule] ?? 0) + n
    for (const f of a.top_files ?? []) fileCounts[f.file_path] = (fileCounts[f.file_path] ?? 0) + f.count
    if (s.duration_ms != null) {
      msSum += s.duration_ms
      msCount += 1
    }
  }

  const topFiles = Object.entries(fileCounts)
    .map(([file_path, count]) => ({ file_path, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)

  return {
    scanned: scans.length,
    completed: completed.length,
    cleanRate: completed.length ? Math.round((clean.length / completed.length) * 100) : 100,
    certainTotal,
    findingsTotal,
    avgMs: msCount ? Math.round(msSum / msCount) : null,
    byRule,
    topFiles,
  }
}
