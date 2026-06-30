"use client"

import { formatDuration, formatRelativeTime, shortRef } from "@/lib/format"
import type { ScanSummary } from "@/lib/types"

/**
 * Scan-history timeline (Check-Box "projects timeline" style): one horizontal
 * bar per scan, width ∝ duration, colored by outcome. Newest first.
 */
function barColor(s: ScanSummary): string {
  if (s.status === "failed") return "bg-sev-certain"
  if (s.status === "queued" || s.status === "running") return "bg-scan"
  return s.analytics?.clean ? "bg-sev-clean" : "bg-sev-high"
}

export function GanttTimeline({ scans }: { scans: ScanSummary[] }) {
  if (scans.length === 0) {
    return <p className="text-sm text-text-faint">No scans yet — your run history will appear here.</p>
  }

  const maxMs = Math.max(1, ...scans.map((s) => s.duration_ms ?? 0))

  return (
    <ul className="space-y-2">
      {scans.map((s) => {
        const pct = Math.max(6, Math.round(((s.duration_ms ?? 0) / maxMs) * 100))
        const findings = s.analytics?.total_findings ?? 0
        return (
          <li key={s.id} className="grid grid-cols-[minmax(120px,160px)_1fr_auto] items-center gap-3 text-sm">
            <span className="truncate font-mono text-xs text-text-muted" title={s.ref}>
              {shortRef(s.ref)}
            </span>
            <div className="h-5 overflow-hidden rounded-md bg-surface">
              <div
                className={`h-full origin-left animate-lollipop-grow rounded-md ${barColor(s)}`}
                style={{ width: `${pct}%` }}
                title={`${formatDuration(s.duration_ms)} · ${findings} findings`}
              />
            </div>
            <span className="tnum w-24 shrink-0 text-right text-xs text-text-faint">
              {formatRelativeTime(s.created_at)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
