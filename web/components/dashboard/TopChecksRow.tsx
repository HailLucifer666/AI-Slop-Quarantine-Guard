"use client"

import { MiniSparkline } from "@/components/charts/MiniSparkline"
import { checkName } from "@/lib/checks"
import { formatNumber } from "@/lib/format"
import type { ScanSummary } from "@/lib/types"

// Severity-axis color per rule (token vars), mirrors SeverityBars.
const RULE_COLOR: Record<string, string> = {
  SQG001: "var(--sev-certain)",
  SQG002: "var(--sev-certain)",
  SQG003: "var(--sev-medium)",
  SQG004: "var(--sev-high)",
  SQG005: "var(--sev-high)",
  SQG006: "var(--sev-high)",
}

/**
 * Top-3 checks by total findings (Stakent "top assets" card style): each card
 * shows the check name, total count, and a per-scan sparkline of that rule.
 */
export function TopChecksRow({ scans }: { scans: ScanSummary[] }) {
  const completed = scans
    .filter((s) => s.status === "completed" && s.created_at && s.analytics)
    .sort((a, b) => (a.created_at! < b.created_at! ? -1 : 1))

  const totals: Record<string, number> = {}
  for (const s of completed) {
    for (const [id, n] of Object.entries(s.analytics!.by_rule ?? {})) {
      totals[id] = (totals[id] ?? 0) + n
    }
  }

  const top = Object.entries(totals)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([id, n]) => ({
      id,
      total: n,
      series: completed.map((s) => s.analytics!.by_rule?.[id] ?? 0),
    }))

  if (top.length === 0) {
    return (
      <div className="glass rounded-lg p-6 text-sm text-text-faint">
        No findings across your scans yet — top checks will appear here once issues are detected.
      </div>
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {top.map((c) => (
        <div key={c.id} className="glass rounded-lg p-5">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-text-faint">{c.id}</span>
            <span className="tnum text-xs text-text-muted">{formatNumber(c.total)} total</span>
          </div>
          <div className="mt-1 font-display text-base font-semibold text-text">{checkName(c.id)}</div>
          <div className="mt-3">
            <MiniSparkline data={c.series} color={RULE_COLOR[c.id] ?? "var(--brand-teal)"} height={40} />
          </div>
        </div>
      ))}
    </div>
  )
}
