import type { AuditEntry, ScanSummary } from "@/lib/types"
import type { HeatCell, RecentTarget, RankedCheck } from "@/lib/useWallData"

/**
 * Deterministic scan fixtures. `NOW` is fixed by `vi.setSystemTime` in each
 * test file so that derive()'s `Date.now()`-driven fields (scannedRecent,
 * time-based sort tiebreaks, formatRelativeTime) are reproducible.
 */
export const NOW = new Date("2026-11-12T06:00:00Z").getTime()

export function mkScan(overrides: Partial<ScanSummary> = {}): ScanSummary {
  return {
    id: 1,
    source: "local",
    ref: "https://github.com/acarg/test-repo",
    status: "completed",
    files_scanned: 100,
    files_skipped: 0,
    duration_ms: 1200,
    error: null,
    analytics: {
      total_findings: 0,
      by_confidence: { CERTAIN: 0, HIGH: 0, MEDIUM: 0 },
      by_rule: {},
      block_eligible: 0,
      top_files: [],
      files_scanned: 100,
      files_skipped: 0,
      files_suppressed: 0,
      clean: true,
      fully_covered: true,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
    coverage: null,
    groups: null,
    progress: null,
    skipped: [],
    suppressed: [],
    created_at: "2026-11-12T06:00:00.000Z",
    completed_at: "2026-11-12T06:00:01.000Z",
    heartbeat_at: null,
    resolved_sha: null,
    content_hash: null,
    file_count: null,
    ingested_at: null,
    engine_versions: null,
    ...overrides,
  }
}

/**
 * The exact derivation fixture used by derive() tests (design §3.2, "QA fixture
 * contract"). Times are absolute ISO strings anchored to NOW (set via
 * vi.setSystemTime). Ordering contract: B first — same block count as A, newer.
 *
 *   A: completed, block=3, created T-2h
 *   B: completed, block=3, created T-1h
 *   C: completed, block=1, created T-30m
 *   D: completed, block=0
 *   E: running
 *   F,G: completed, block=2  (verify slice(0,5) cap)
 *   H: completed, analytics null  (verify null-analytics exclusion)
 */
export const FIXTURE_SCANS: ScanSummary[] = [
  mkScan({
    id: 1,
    ref: "https://github.com/acarg/sloppy-backend",
    status: "completed",
    created_at: new Date(NOW - 2 * 60 * 60 * 1000).toISOString(),
    analytics: {
      total_findings: 4,
      by_confidence: { CERTAIN: 2, HIGH: 1, MEDIUM: 1 },
      by_rule: { SQG001: 5, SQG004: 3 },
      block_eligible: 3,
      top_files: [{ file_path: "backend/ai/gen.py", count: 4 }],
      files_scanned: 1200,
      files_skipped: 0,
      files_suppressed: 0,
      clean: false,
      fully_covered: true,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
  }),
  mkScan({
    id: 2,
    ref: "https://github.com/acarg/secret-leaker",
    status: "completed",
    created_at: new Date(NOW - 1 * 60 * 60 * 1000).toISOString(),
    analytics: {
      total_findings: 3,
      by_confidence: { CERTAIN: 1, HIGH: 2, MEDIUM: 0 },
      by_rule: { SQG002: 6, SQG001: 2 },
      block_eligible: 3,
      top_files: [],
      files_scanned: 5100,
      files_skipped: 0,
      files_suppressed: 0,
      clean: false,
      fully_covered: false,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
  }),
  mkScan({
    id: 3,
    ref: "https://github.com/acarg/typosquat",
    status: "completed",
    created_at: new Date(NOW - 30 * 60 * 1000).toISOString(),
    analytics: {
      total_findings: 1,
      by_confidence: { CERTAIN: 0, HIGH: 0, MEDIUM: 1 },
      by_rule: { SQG007: 1 },
      block_eligible: 1,
      top_files: [],
      files_scanned: 300,
      files_skipped: 0,
      files_suppressed: 0,
      clean: false,
      fully_covered: true,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
  }),
  mkScan({
    id: 4,
    ref: "https://github.com/acarg/clean-project",
    status: "completed",
    created_at: new Date(NOW - 4 * 60 * 60 * 1000).toISOString(),
    analytics: {
      total_findings: 0,
      by_confidence: { CERTAIN: 0, HIGH: 0, MEDIUM: 0 },
      by_rule: {},
      block_eligible: 0,
      top_files: [],
      files_scanned: 80,
      files_skipped: 0,
      files_suppressed: 0,
      clean: true,
      fully_covered: true,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
  }),
  mkScan({
    id: 5,
    ref: "https://github.com/acarg/running-scan",
    status: "running",
    created_at: new Date(NOW - 10 * 60 * 1000).toISOString(),
    analytics: null,
  }),
  mkScan({
    id: 6,
    ref: "https://github.com/acarg/mid-block",
    status: "completed",
    created_at: new Date(NOW - 3 * 60 * 60 * 1000).toISOString(),
    analytics: {
      total_findings: 3,
      by_confidence: { CERTAIN: 0, HIGH: 3, MEDIUM: 0 },
      by_rule: { SQG006: 3 },
      block_eligible: 2,
      top_files: [],
      files_scanned: 450,
      files_skipped: 0,
      files_suppressed: 0,
      clean: false,
      fully_covered: true,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
  }),
  mkScan({
    id: 7,
    ref: "https://github.com/acarg/old-block",
    status: "completed",
    created_at: new Date(NOW - 5 * 60 * 60 * 1000).toISOString(),
    analytics: {
      total_findings: 2,
      by_confidence: { CERTAIN: 2, HIGH: 0, MEDIUM: 0 },
      by_rule: { SQG001: 2 },
      block_eligible: 2,
      top_files: [],
      files_scanned: 200,
      files_skipped: 0,
      files_suppressed: 0,
      clean: false,
      fully_covered: true,
      rules_ran: 8,
      rules_total: 8,
      rules_incomplete: 0,
      unexamined_files: 0,
    },
  }),
  mkScan({
    id: 8,
    ref: "https://github.com/acarg/no-analytics",
    status: "completed",
    created_at: new Date(NOW - 6 * 60 * 60 * 1000).toISOString(),
    analytics: null,
  }),
]

export const FIXTURE_AUDIT: AuditEntry[] = [
  { id: 1, action: "scan.created", details: { ref: "https://github.com/acarg/sloppy-backend" }, created_at: new Date(NOW - 2 * 60 * 60 * 1000).toISOString() },
  { id: 2, action: "scan.running", details: { scan_id: 1 }, created_at: new Date(NOW - 2 * 60 * 60 * 1000 + 1000).toISOString() },
  { id: 3, action: "scan.completed", details: { ref: "https://github.com/acarg/sloppy-backend", total_findings: 4, block_eligible: 3 }, created_at: new Date(NOW - 2 * 60 * 60 * 1000 + 2000).toISOString() },
  { id: 4, action: "scan.failed", details: { ref: "https://github.com/acarg/bad-ref", reason: "timeout" }, created_at: new Date(NOW - 90 * 60 * 1000).toISOString() },
  { id: 5, action: "scan.completed", details: { ref: "https://github.com/acarg/secret-leaker", total_findings: 3, block_eligible: 3 }, created_at: new Date(NOW - 1 * 60 * 60 * 1000 + 2000).toISOString() },
  { id: 6, action: "scan.shadow_block", details: { scan_id: 99, would_block: 1, note: "shadow only" }, created_at: new Date(NOW - 80 * 60 * 1000).toISOString() },
  { id: 7, action: "settings.updated", details: { key: "block_mode", value: true }, created_at: new Date(NOW - 5 * 60 * 1000).toISOString() },
]

export function mkHeatCell(day: string, count: number): HeatCell {
  return { day, count }
}

export function mkRecentTarget(id: number, ref: string, status: ScanSummary["status"], clean: boolean, findings: number, sev: "clean" | "certain" | "high" | "medium", filesScanned: number): RecentTarget {
  return { id, ref, status, clean, findings, sev, filesScanned }
}

export const FIXTURE_RECENT_TARGETS: RecentTarget[] = [
  mkRecentTarget(1, "https://github.com/acarg/secret-leaker", "completed", false, 3, "certain", 5100),
  mkRecentTarget(2, "https://github.com/acarg/clean-project", "completed", true, 0, "clean", 80),
  mkRecentTarget(3, "https://github.com/acarg/running-scan", "running", false, 0, "high", 0),
]

export function mkRankedCheck(id: string, name: string, count: number, sev: "clean" | "certain" | "high" | "medium"): RankedCheck {
  return { id, name, count, sev }
}

export const FIXTURE_RANKED_CHECKS: RankedCheck[] = [
  mkRankedCheck("SQG002", "Leaked secret", 6, "certain"),
  mkRankedCheck("SQG001", "Hallucinated package", 5, "certain"),
  mkRankedCheck("SQG006", "Security issue", 3, "high"),
  mkRankedCheck("SQG004", "Vulnerable dependency", 3, "high"),
  mkRankedCheck("SQG007", "Possible typosquat", 1, "medium"),
]
