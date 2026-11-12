"use client"

/**
 * The Command Wall's single data source. Polls the real scan + audit endpoints
 * on an interval (pauses when the tab is hidden or `paused`), then derives every
 * panel's numbers from real records — no fabrication. Empty DB → zeroed values
 * and empty arrays, which the panels render as honest empty states.
 */
import { useEffect, useMemo, useRef, useState } from "react"

import { listAudit, listScans } from "@/lib/api"
import { CHECKS, checkName } from "@/lib/checks"
import type { AuditEntry, ScanSummary } from "@/lib/types"

export type Sev = "certain" | "high" | "medium" | "clean"

/** Each rule's severity tier, straight from the one check-metadata source. */
const RULE_SEV: Record<string, Sev> = Object.fromEntries(
  Object.values(CHECKS).map((c) => [c.id, c.severity]),
)

export interface RankedCheck {
  id: string
  name: string
  count: number
  sev: Sev
}

export interface GlobeNode {
  id: number
  ref: string
  sev: Sev // worst confidence present (or clean)
  weight: number // total findings → beam height / arc emphasis
  at: number // epoch ms (for ordering / replay)
}

export interface HeatCell {
  day: string // ISO date (yyyy-mm-dd)
  count: number
}

export interface RecentTarget {
  id: number
  ref: string
  status: ScanSummary["status"]
  clean: boolean
  findings: number
  sev: Sev
  /** Real per-scan read volume (ScanSummary.files_scanned) — globe ring thickness. */
  filesScanned: number
}

/** One row of the Fix First queue: a recent scan ranked by how many provable,
 * would-block findings it holds (spec §3.2). Derived purely from ScanSummary —
 * no per-scan findings fetches (listScans caps at 50 rows; accepted in the plan). */
export interface FixFirstRow {
  scanId: number
  ref: string
  blockEligible: number // analytics.block_eligible
  advisories: number // max(0, analytics.total_findings - analytics.block_eligible)
  topChecks: { id: string; name: string; count: number }[] // ≤2, from by_rule, count desc
  sev: Sev // worst confidence tier present (worstSev())
  at: number // created_at epoch ms (recency tiebreak)
}

export interface WallData {
  scanned: number
  scannedRecent: number // created in the last 10 min
  completed: number
  slopToday: number // findings from scans created today
  findingsTotal: number
  certainTotal: number
  highTotal: number // sum of analytics.by_confidence.HIGH over completed scans
  mediumTotal: number // sum of analytics.by_confidence.MEDIUM over completed scans
  incompleteCoverage: number // completed scans with analytics.fully_covered === false
  blockEligible: number // provable, would-block findings (advisory = findingsTotal - this)
  cleanRate: number // 0–100
  cleanPasses: number
  fixFirst: FixFirstRow[] // ≤5, block_eligible desc → created_at desc → id desc
  byCheck: RankedCheck[] // ranked desc
  topFiles: { file_path: string; count: number }[]
  heatmap: HeatCell[] // last 13 weeks
  recentTargets: RecentTarget[]
  feed: AuditEntry[] // newest first
  globe: GlobeNode[] // one node per scan, newest last
  severitySeries: { certain: number; high: number; medium: number }[] // per completed scan, chrono
  /** Max id among completed scans, else null — the beam-sweep trigger (spec §10.4). */
  latestCompletedId: number | null
  /** Green/Red only for now — real signals (any recent scan failed). Yellow (a
   * completed scan with degraded analyzer coverage) needs the per-analyzer
   * `coverage[]`/`trust_status` field the backend doesn't expose yet (Phase 2) —
   * do not fabricate it before that field exists. */
  trustStatus: "green" | "red"
  hasRecentFailure: boolean
}

const EMPTY: WallData = {
  scanned: 0,
  scannedRecent: 0,
  completed: 0,
  slopToday: 0,
  findingsTotal: 0,
  certainTotal: 0,
  highTotal: 0,
  mediumTotal: 0,
  incompleteCoverage: 0,
  blockEligible: 0,
  cleanRate: 100,
  cleanPasses: 0,
  fixFirst: [],
  byCheck: [],
  topFiles: [],
  heatmap: [],
  recentTargets: [],
  feed: [],
  globe: [],
  severitySeries: [],
  latestCompletedId: null,
  trustStatus: "green",
  hasRecentFailure: false,
}

const TEN_MIN = 10 * 60 * 1000
const HEAT_DAYS = 13 * 7 // 13 weeks

function worstSev(a: ScanSummary["analytics"]): Sev {
  if (!a) return "clean"
  if ((a.by_confidence?.CERTAIN ?? 0) > 0) return "certain"
  if ((a.by_confidence?.HIGH ?? 0) > 0) return "high"
  if ((a.by_confidence?.MEDIUM ?? 0) > 0) return "medium"
  return "clean"
}

function isoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10)
}

/** Derive every panel's numbers from real records. Exported for QA (the FixFirst
 * ranking fixture contract in docs/design/dashboard-overhaul.md §3.2 tests this
 * pure function directly). */
export function derive(scans: ScanSummary[], audit: AuditEntry[]): WallData {
  if (scans.length === 0 && audit.length === 0) return EMPTY

  const now = Date.now()
  const todayKey = isoDay(now)
  const completed = scans.filter((s) => s.status === "completed")
  const completedChrono = completed
    .filter((s) => s.created_at)
    .sort((a, b) => (a.created_at! < b.created_at! ? -1 : 1))

  let findingsTotal = 0
  let certainTotal = 0
  let highTotal = 0
  let mediumTotal = 0
  let incompleteCoverage = 0
  let blockEligible = 0
  let cleanPasses = 0
  let slopToday = 0
  const ruleCounts: Record<string, number> = {}
  const fileCounts: Record<string, number> = {}
  const heatBuckets: Record<string, number> = {}

  for (const s of completed) {
    const a = s.analytics
    if (a?.clean) cleanPasses += 1
    if (!a) continue
    findingsTotal += a.total_findings
    certainTotal += a.by_confidence?.CERTAIN ?? 0
    highTotal += a.by_confidence?.HIGH ?? 0
    mediumTotal += a.by_confidence?.MEDIUM ?? 0
    if (a.fully_covered === false) incompleteCoverage += 1
    blockEligible += a.block_eligible ?? 0
    for (const [id, n] of Object.entries(a.by_rule ?? {})) ruleCounts[id] = (ruleCounts[id] ?? 0) + n
    for (const f of a.top_files ?? []) fileCounts[f.file_path] = (fileCounts[f.file_path] ?? 0) + f.count
    if (s.created_at && isoDay(new Date(s.created_at).getTime()) === todayKey) {
      slopToday += a.total_findings
    }
  }

  // Heatmap — every scan (any status) bucketed by created day.
  for (const s of scans) {
    if (!s.created_at) continue
    const key = isoDay(new Date(s.created_at).getTime())
    heatBuckets[key] = (heatBuckets[key] ?? 0) + 1
  }
  const heatmap: HeatCell[] = []
  for (let i = HEAT_DAYS - 1; i >= 0; i--) {
    const key = isoDay(now - i * 24 * 60 * 60 * 1000)
    heatmap.push({ day: key, count: heatBuckets[key] ?? 0 })
  }

  const byCheck: RankedCheck[] = Object.entries(ruleCounts)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([id, count]) => ({
      id,
      name: CHECKS[id]?.name ?? checkName(id),
      count,
      sev: RULE_SEV[id] ?? "medium",
    }))

  const topFiles = Object.entries(fileCounts)
    .map(([file_path, count]) => ({ file_path, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)

  const scannedRecent = scans.filter(
    (s) => s.created_at && now - new Date(s.created_at).getTime() <= TEN_MIN,
  ).length

  // Fix First — recent scans ranked by block-eligible count (spec §3.2, exact):
  // completed + analytics present + block_eligible > 0 + created_at present,
  // then block_eligible DESC → created_at DESC → id DESC, top 5.
  const fixFirst: FixFirstRow[] = scans
    .filter(
      (s) =>
        s.status === "completed" &&
        s.analytics != null &&
        (s.analytics.block_eligible ?? 0) > 0 &&
        s.created_at != null,
    )
    .sort((a, b) => {
      const byBlock = (b.analytics?.block_eligible ?? 0) - (a.analytics?.block_eligible ?? 0)
      if (byBlock !== 0) return byBlock
      const byAt = new Date(b.created_at!).getTime() - new Date(a.created_at!).getTime()
      if (byAt !== 0) return byAt
      return b.id - a.id
    })
    .slice(0, 5)
    .map((s): FixFirstRow | null => {
      const a = s.analytics
      const createdAt = s.created_at
      if (!a || !createdAt) return null // filter guarantees both; keeps TS honest
      return {
        scanId: s.id,
        ref: s.ref,
        blockEligible: a.block_eligible ?? 0,
        advisories: Math.max(0, a.total_findings - (a.block_eligible ?? 0)),
        topChecks: Object.entries(a.by_rule ?? {})
          .filter(([, n]) => n > 0)
          .sort((x, y) => y[1] - x[1])
          .slice(0, 2)
          .map(([id, count]) => ({ id, name: CHECKS[id]?.name ?? id, count })),
        sev: worstSev(a),
        at: new Date(createdAt).getTime(),
      }
    })
    .filter((r): r is FixFirstRow => r != null)

  const recentTargets: RecentTarget[] = [...scans]
    .filter((s) => s.created_at)
    .sort((a, b) => (a.created_at! < b.created_at! ? 1 : -1))
    .slice(0, 8)
    .map((s) => ({
      id: s.id,
      ref: s.ref,
      status: s.status,
      clean: !!s.analytics?.clean,
      findings: s.analytics?.total_findings ?? 0,
      sev: worstSev(s.analytics),
      filesScanned: s.files_scanned,
    }))

  const globe: GlobeNode[] = completedChrono.map((s) => ({
    id: s.id,
    ref: s.ref,
    sev: worstSev(s.analytics),
    weight: s.analytics?.total_findings ?? 0,
    at: s.created_at ? new Date(s.created_at).getTime() : 0,
  }))

  const severitySeries = completedChrono.map((s) => ({
    certain: s.analytics?.by_confidence?.CERTAIN ?? 0,
    high: s.analytics?.by_confidence?.HIGH ?? 0,
    medium: s.analytics?.by_confidence?.MEDIUM ?? 0,
  }))

  const hasRecentFailure = scans.some((s) => s.status === "failed")

  const latestCompletedId = completed.reduce<number | null>(
    (acc, s) => (acc == null || s.id > acc ? s.id : acc),
    null,
  )

  return {
    scanned: scans.length,
    scannedRecent,
    completed: completed.length,
    slopToday,
    findingsTotal,
    certainTotal,
    highTotal,
    mediumTotal,
    incompleteCoverage,
    blockEligible,
    cleanRate: completed.length ? Math.round((cleanPasses / completed.length) * 100) : 100,
    cleanPasses,
    fixFirst,
    byCheck,
    topFiles,
    heatmap,
    recentTargets,
    feed: audit,
    globe,
    severitySeries,
    latestCompletedId,
    trustStatus: hasRecentFailure ? "red" : "green",
    hasRecentFailure,
  }
}

export function useWallData({ paused = false, intervalMs = 15000 } = {}) {
  const [scans, setScans] = useState<ScanSummary[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<number | null>(null)
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | null = null

    async function tick() {
      if (!alive) return
      // Skip the fetch entirely when paused or backgrounded — but keep the loop alive.
      if (!pausedRef.current && (typeof document === "undefined" || !document.hidden)) {
        try {
          const [s, a] = await Promise.all([listScans(), listAudit().catch(() => [])])
          if (!alive) return
          setScans(s)
          setAudit(a)
          setError(null)
          setLastUpdated(Date.now())
        } catch (e) {
          if (alive) setError(e instanceof Error ? e.message : "Failed to load")
        } finally {
          if (alive) setLoading(false)
        }
      }
      timer = setTimeout(tick, intervalMs)
    }

    tick()
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
  }, [intervalMs])

  const data = useMemo(() => derive(scans, audit), [scans, audit])
  // Real reachability: true only after a successful fetch and while not erroring.
  const online = lastUpdated !== null && !error
  return { data, scans, online, loading, error, lastUpdated }
}
