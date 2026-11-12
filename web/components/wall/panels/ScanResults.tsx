"use client"

import { useState } from "react"
import { AlertTriangle, Check, CheckCircle2, Copy, FileWarning } from "lucide-react"

import { CoveragePanel } from "@/components/findings/CoveragePanel"
import { FindingCard } from "@/components/findings/FindingCard"
import { GroupedFindings } from "@/components/findings/GroupedFindings"
import { Donut, RingGauge, type Segment } from "@/components/wall/charts/RadialCharts"
import { CHECKS, CONFIDENCE_LABEL, CONFIDENCE_ORDER } from "@/lib/checks"
import { buildFixPrompt } from "@/lib/exportFindings"
import { formatDuration, formatNumber, shortRef } from "@/lib/format"
import type { ScanDetail } from "@/lib/types"

/** Per-rule accent colors (shared with the Activity Spectrum lanes). */
const RULE_COLOR: Record<string, string> = {
  SQG001: "#ff3d8b",
  SQG002: "#ff3b5c",
  SQG003: "#ffc83d",
  SQG004: "#ff8a3d",
  SQG005: "#8b5cf6",
  SQG006: "#16e0e0",
  // SQG007 was missing here, so typosquat findings were counted by the backend but
  // never appeared in the per-check strip or the "By check" donut.
  SQG007: "#4d7cff",
  SQG009: "#5ef08a",
}
const RULE_ORDER = ["SQG001", "SQG002", "SQG003", "SQG004", "SQG005", "SQG006", "SQG007", "SQG009"]

// Cap how many finding cards mount per group at once. A 1500+-file scan can produce
// thousands of findings; committing them all synchronously froze the page. Reveal
// the rest on demand in chunks of this size.
const RENDER_CAP = 100

/**
 * The scan result view — headline stats, radial charts (per-rule + severity +
 * file coverage), a readable per-check strip, and the findings. Rendered inline
 * on the scan page the moment analysis finishes, and on the analyses detail page.
 * Every number derives from real analytics; nothing is invented.
 */
export function ScanResults({ scan }: { scan: ScanDetail }) {
  const [copied, setCopied] = useState(false)
  const [fallback, setFallback] = useState<string | null>(null)
  const [limits, setLimits] = useState<Record<string, number>>({})
  const a = scan.analytics

  async function copyForAI() {
    const text = buildFixPrompt(scan)
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setFallback(text)
    }
  }

  const advisory = a ? Math.max(0, a.total_findings - a.block_eligible) : 0
  const grouped = CONFIDENCE_ORDER
    .map((c) => ({ confidence: c, items: scan.findings.filter((f) => f.confidence === c) }))
    .filter((g) => g.items.length > 0)

  const ruleSegments: Segment[] = RULE_ORDER
    .map((id) => ({ label: CHECKS[id]?.name ?? id, value: a?.by_rule?.[id] ?? 0, color: RULE_COLOR[id] }))
  const sevSegments: Segment[] = [
    { label: "Certain", value: a?.by_confidence?.CERTAIN ?? 0, color: "var(--sev-certain)" },
    { label: "High", value: a?.by_confidence?.HIGH ?? 0, color: "var(--sev-high)" },
    { label: "Medium", value: a?.by_confidence?.MEDIUM ?? 0, color: "var(--sev-medium)" },
  ]
  const totalFiles = (a?.files_scanned ?? 0) + (a?.files_skipped ?? 0)

  const TILES = a
    ? [
        { label: "Findings", value: a.total_findings, color: "var(--text)" },
        { label: "Block-eligible", value: a.block_eligible, color: a.block_eligible > 0 ? "var(--sev-certain)" : "var(--sev-clean)" },
        { label: "Advisory", value: advisory, color: "var(--sev-medium)" },
        { label: "Files scanned", value: a.files_scanned, color: "var(--text)" },
      ]
    : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm" style={{ color: "var(--text)" }}>{shortRef(scan.ref)}</div>
          <div className="text-xs" style={{ color: "var(--text-faint)" }}>{scan.source} · scan #{scan.id} · {scan.status} · {formatDuration(scan.duration_ms)}</div>
        </div>
        {scan.findings.length > 0 && (
          <button
            onClick={copyForAI}
            title="Copies every finding as a structured prompt — paste into your AI to fix them all at once."
            className="wall-cta-secondary inline-flex w-auto items-center gap-2 text-sm"
          >
            {copied ? <><Check className="h-4 w-4" aria-hidden /> Copied</> : <><Copy className="h-4 w-4" aria-hidden /> Copy for AI</>}
          </button>
        )}
      </div>

      {fallback && (
        <div className="space-y-2 rounded-md p-3" style={{ border: "1px solid var(--line)" }}>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Clipboard was blocked — select all (Ctrl/Cmd-A) inside the box and copy manually.</p>
          <textarea readOnly value={fallback} onFocus={(e) => e.currentTarget.select()} autoFocus className="h-48 w-full resize-y rounded bg-transparent p-2 font-mono text-xs" style={{ color: "var(--text)", border: "1px solid var(--line)" }} />
        </div>
      )}

      {/* Headline stat tiles — large + readable */}
      {a && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {TILES.map((t) => (
            <div key={t.label} className="wall-card flex flex-col gap-1 p-4">
              <div className="wall-label">{t.label}</div>
              <div className="wall-num text-4xl leading-none" style={{ color: t.color }}>{formatNumber(t.value)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Radial charts */}
      {a && (
        <div className="grid grid-cols-1 justify-items-center gap-6 sm:grid-cols-3">
          <Donut title="By check" segments={ruleSegments} centerSub="findings" />
          <Donut title="By severity" segments={sevSegments} centerSub="findings" />
          <RingGauge title="File coverage" value={a.files_scanned} max={totalFiles} color="var(--accent-cyan)" centerSub={`of ${formatNumber(totalFiles)}`} />
        </div>
      )}

      {/* Per-check strip — all 6 analyzers, what each found (0 = clean) */}
      {a && (
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
          {RULE_ORDER.map((id) => {
            const count = a.by_rule?.[id] ?? 0
            return (
              <div key={id} className="flex items-center justify-between gap-3 rounded-lg p-3" style={{ border: "1px solid var(--line)", background: "var(--bg-deep)" }}>
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: count > 0 ? RULE_COLOR[id] : "var(--sev-clean)", boxShadow: count > 0 ? `0 0 8px ${RULE_COLOR[id]}` : "none" }} aria-hidden />
                  <span className="truncate text-sm" style={{ color: "var(--text)" }}>{CHECKS[id]?.name ?? id}</span>
                </span>
                <span className="wall-num text-lg" style={{ color: count > 0 ? "var(--text)" : "var(--text-faint)" }}>{count}</span>
              </div>
            )
          })}
        </div>
      )}

      {scan.files_skipped > 0 && (
        <div className="flex items-start gap-2 rounded-md p-3 text-sm" style={{ color: "var(--text-muted)", background: "rgba(255,200,61,0.06)", border: "1px solid rgba(255,200,61,0.2)" }}>
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--sev-medium)" }} aria-hidden />
          <span>{scan.files_skipped} file(s) skipped (size/type caps) — not analyzed, so some findings may be missing. We never pretend to have checked what we didn&apos;t.</span>
        </div>
      )}

      {/* Different cause, different sentence. This one is the repository's own ignore
          rules excluding part of itself; the banner above is our size/type caps. Both
          force `clean` false server-side (coverage.summarize), so this can never sit
          next to an "All clear". */}
      {(a?.files_suppressed ?? 0) > 0 && (
        <div className="flex items-start gap-2 rounded-md p-3 text-sm" style={{ color: "var(--text-muted)", background: "rgba(255,200,61,0.06)", border: "1px solid rgba(255,200,61,0.2)" }}>
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--sev-medium)" }} aria-hidden />
          <span>
            {a?.files_suppressed} director{(a?.files_suppressed ?? 0) === 1 ? "y was" : "ies were"} excluded by this
            repository&apos;s own ignore rules and {(a?.files_suppressed ?? 0) === 1 ? "was" : "were"} not examined.
            A repository can&apos;t be reported as clean while part of it went unread.
          </span>
        </div>
      )}

      {/* Verdict. "All clear" requires that every check actually ran — a scan with
          nothing found but three checks skipped is inconclusive, and says so. */}
      {scan.status === "completed" && scan.findings.length === 0 && (
        a?.clean ? (
          <div className="flex flex-col items-center gap-3 rounded-xl p-10 text-center" style={{ border: "1px solid var(--line)" }}>
            <CheckCircle2 className="h-10 w-10" style={{ color: "var(--sev-clean)" }} aria-hidden />
            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text)" }}>All clear</h2>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              All {a.rules_total} checks ran and found nothing.
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 rounded-xl p-10 text-center" style={{ border: "1px solid rgba(255,200,61,0.25)", background: "rgba(255,200,61,0.04)" }}>
            <AlertTriangle className="h-10 w-10" style={{ color: "var(--sev-medium)" }} aria-hidden />
            <h2 className="font-display text-xl font-bold" style={{ color: "var(--text)" }}>
              No problems found in what was scanned
            </h2>
            <p className="max-w-xl text-sm" style={{ color: "var(--text-muted)" }}>
              {a
                ? `${a.rules_ran} of ${a.rules_total} checks ran. This is not a clean bill of health — see what was checked below.`
                : "Coverage wasn't recorded for this scan, so we can't say every check ran."}
            </p>
          </div>
        )
      )}

      {/* Clustered issues, so repetition can't bury severity. */}
      <GroupedFindings groups={scan.groups} findings={scan.findings} />

      {/* Fallback for scans stored before grouping existed. */}
      {!scan.groups && grouped.map((g) => {
        const limit = limits[g.confidence] ?? RENDER_CAP
        const remaining = g.items.length - limit
        return (
          <section key={g.confidence} className="space-y-3">
            <h3 className="wall-label">
              {g.confidence} <span style={{ color: "var(--text-faint)" }}>· {CONFIDENCE_LABEL[g.confidence]} ({g.items.length})</span>
            </h3>
            {g.items.slice(0, limit).map((f, i) => <FindingCard key={`${g.confidence}-${i}`} finding={f} />)}
            {remaining > 0 && (
              <button
                onClick={() => setLimits((p) => ({ ...p, [g.confidence]: limit + RENDER_CAP }))}
                className="wall-cta-secondary inline-flex w-auto items-center gap-2 text-sm"
              >
                Show {Math.min(remaining, RENDER_CAP)} more · {remaining} hidden
              </button>
            )}
          </section>
        )
      })}

      {/* What ran, what didn't, and why. */}
      <CoveragePanel coverage={scan.coverage} />

      {/* Provenance — the exact snapshot analyzed, so the result is reproducible. */}
      {(scan.resolved_sha || scan.content_hash) && (
        <section className="wall-card p-4">
          <h3 className="wall-label">What was analyzed</h3>
          <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
            {scan.resolved_sha && (
              <div className="flex gap-2">
                <dt style={{ color: "var(--text-faint)" }}>Commit</dt>
                <dd className="font-mono" style={{ color: "var(--text)" }}>{scan.resolved_sha.slice(0, 12)}</dd>
              </div>
            )}
            {scan.content_hash && (
              <div className="flex gap-2">
                <dt style={{ color: "var(--text-faint)" }}>Content hash</dt>
                <dd className="font-mono" style={{ color: "var(--text)" }}>{scan.content_hash.slice(0, 16)}…</dd>
              </div>
            )}
            {scan.file_count !== null && (
              <div className="flex gap-2">
                <dt style={{ color: "var(--text-faint)" }}>Files analyzed</dt>
                <dd className="wall-num" style={{ color: "var(--text)" }}>{formatNumber(scan.file_count)}</dd>
              </div>
            )}
            {scan.engine_versions?.rules_version && (
              <div className="flex gap-2">
                <dt style={{ color: "var(--text-faint)" }}>Rule set</dt>
                <dd className="font-mono" style={{ color: "var(--text)" }}>v{scan.engine_versions.rules_version}</dd>
              </div>
            )}
          </dl>
          <p className="mt-2 text-xs" style={{ color: "var(--text-faint)" }}>
            Re-scanning identical code produces a new scan number with this same content hash —
            proof it was freshly re-analyzed, not served from a cache.
          </p>
        </section>
      )}
    </div>
  )
}
