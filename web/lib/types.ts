/**
 * Frontend mirror of the Stage 2 scan API JSON (api/app/store.py _row_to_dict +
 * api/app/scan.py finding_to_dict/aggregate). Keep these in lockstep with the backend.
 */

export type Confidence = "CERTAIN" | "HIGH" | "MEDIUM"
export type ScanStatus = "queued" | "running" | "completed" | "failed"
export type ScanSource = "url" | "zip" | "local"
export type RuleId = "SQG001" | "SQG002" | "SQG003" | "SQG004" | "SQG005" | "SQG006" | "SQG007"

export interface Evidence {
  snippet: string
  context_before: string[]
  context_after: string[]
}

export interface Advisory {
  id: string
  url: string
}

/** How a finding can be fixed.
 *
 * `kind: "patch"` means the replacement was derived mechanically from an authoritative
 * source (an OSV-named fixed version, a Semgrep autofix), so it is safe to render as a
 * one-click apply. Anything else is `"guidance"` — prose only, never a fake diff.
 */
export interface Remediation {
  kind: "patch" | "guidance"
  text: string
  suggested_replacement: string | null
  basis: string
  applicable: boolean
}

export interface Finding {
  rule_id: string
  category: string
  confidence: Confidence
  block_eligible: boolean
  file_path: string
  line_start: number
  line_end: number
  message: string
  tool: string
  fix_suggestion: string | null
  evidence: Evidence
  /** Provenance. Render these — a finding a user can't trace is a claim, not a result. */
  analyzer_version: string
  rule_version: string
  tool_version: string
  evidence_hash: string
  /** Content-derived id, stable across scans and line moves. */
  fingerprint: string
  /** Empty means "not known", never "none apply" — do not render as "no CWE". */
  cwe: string[]
  advisories: Advisory[]
  severity: string | null
  cvss_score: number | null
  cvss_vector: string | null
  fix_versions: string[]
  rule_url: string
  remediation: Remediation | null
}

/** Status of one check on one scan. Only `ran` makes "found nothing" meaningful. */
export type RuleStatus =
  | "ran"
  | "partial"
  | "not_run_unsupported"
  | "not_run_engine_missing"
  | "not_run_disabled"
  | "errored"
  | "timed_out"

export interface RuleCoverage {
  rule_id: string
  title: string
  status: RuleStatus
  engine: string
  engine_version: string
  duration_ms: number | null
  findings: number
  /** Human-readable, e.g. ["Python (128 files)"] or ["npm"]. */
  covered: string[]
  /** What this check could NOT read, e.g. ["SQL (80 files)", "semgrep not installed"]. */
  not_covered: string[]
  detail: string
}

/** Per-rule coverage rollup. This is what makes a zero-findings result interpretable:
 * `clean` is true only when every check reached a conclusive result AND found nothing. */
export interface Coverage {
  rules_total: number
  rules_ran: number
  rules_incomplete: number
  fully_covered: boolean
  clean: boolean
  rules: RuleCoverage[]
}

/** One issue and every place it occurs, so volume can't bury severity. */
export interface FindingGroupOccurrence {
  file_path: string
  line_start: number
  line_end: number
  snippet: string
  fingerprint: string
}

export interface FindingGroup {
  key: string
  rule_id: string
  title: string
  confidence: Confidence
  /** True total, even when `occurrences` is capped. Always show this number. */
  count: number
  file_count: number
  grouped: boolean
  occurrences_shown: number
  occurrences: FindingGroupOccurrence[]
}

export interface FindingGroups {
  groups_total: number
  findings_total: number
  collapsed_groups: number
  groups: FindingGroup[]
}

export interface TopFile {
  file_path: string
  count: number
}

export interface Analytics {
  total_findings: number
  by_confidence: Record<string, number> // CERTAIN / HIGH / MEDIUM
  by_rule: Record<string, number> // SQG001..SQG006 -> count
  block_eligible: number
  top_files: TopFile[]
  files_scanned: number
  files_skipped: number
  /** Every check ran AND found nothing. NOT the same as `total_findings === 0` — a scan
   * where three checks could not run is inconclusive, not clean. */
  clean: boolean
  fully_covered: boolean
  rules_ran: number
  rules_total: number
  rules_incomplete: number
}

/** Live phase progress while a scan runs (cleared on finish). Honest: real phase
 * index over the 6 analyzers, no invented %/ETA. */
export interface ScanProgress {
  phase: string // dependencies | placeholders | secrets | vulnerabilities | sast | licenses | reporting
  index: number // 0..total
  total: number // 6
  findings_so_far: number
  files_total: number
}

export interface ScanSummary {
  id: number
  source: ScanSource
  ref: string
  status: ScanStatus
  files_scanned: number
  files_skipped: number
  duration_ms: number | null
  error: string | null
  analytics: Analytics | null
  coverage: Coverage | null
  /** Clustered findings, computed server-side so the dashboard and the PR comment
   * always report the same totals. Null for scans stored before grouping existed. */
  groups: FindingGroups | null
  progress: ScanProgress | null
  skipped: string[]
  created_at: string | null
  completed_at: string | null
  heartbeat_at: string | null
  /** Provenance: exactly what was analyzed. A re-scan of unchanged code produces a NEW
   * id with a MATCHING content_hash — evidence of a fresh run, not a cached one. */
  resolved_sha: string | null
  content_hash: string | null
  file_count: number | null
  ingested_at: string | null
  engine_versions: { rules_version?: string; engines?: Record<string, string | null> } | null
}

export interface ScanDetail extends ScanSummary {
  findings: Finding[]
}

export interface ScanListPage {
  scans: ScanSummary[]
  total: number
  has_more: boolean
}

/** GET /api/scans/summary — cross-scan rollup for the dashboard overview. */
export interface ScansSummary {
  scanned_in_range: number
  clean_pass_rate: number
  /** How many of those scans had at least one check that couldn't finish — the caveat
   * that belongs next to any pass rate. */
  scans_with_incomplete_coverage: number
  certain_total: number
  findings_total: number
  by_rule: Record<string, number>
  top_files: TopFile[]
}

export const TERMINAL_STATUSES: ScanStatus[] = ["completed", "failed"]
export const isTerminal = (s: ScanStatus) => TERMINAL_STATUSES.includes(s)

/** The Crew (Phase 7) — advisory AI explanation of one finding. */
export interface Explanation {
  explanation: string
  why_it_matters: string
  how_to_fix: string
}

/** Global gate settings (Phase 8). Saved prefs only — blocking enforcement is Phase 9. */
export interface AppSettings {
  block_mode: boolean
  blocked_rules: string[]
  retention_days: number
  updated_at: string | null
}

/** One audit-trail entry — the lifecycle record of a Guard action. */
export interface AuditEntry {
  id: number
  action: string
  details: Record<string, unknown> | null
  created_at: string | null
}
