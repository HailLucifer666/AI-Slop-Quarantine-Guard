"use client"

import { AlertTriangle, Info, Shield, ShieldAlert, ShieldCheck } from "lucide-react"
import type { CSSProperties } from "react"

import { formatNumber } from "@/lib/format"
import { useCountUp } from "@/components/wall/hooks"

function chipColor(color: string): CSSProperties {
  return { "--chip-color": color } as CSSProperties
}

/**
 * Quarantine Status hero (spec §2a.2) — THE dominant statement answering "is my
 * code clean". One figure + severity chips (icon+text+color) + context line with
 * the honest incomplete-coverage caveat. The whole tile is one button → /analyses
 * (the inline chips share that destination, so they render as chips, not nested
 * buttons — nested <button> would be invalid HTML).
 *
 * Lives in its own file: Next.js page modules may only export known keys, so a
 * page-file export would fail `tsc`/`next build` (tested via components/wall/Hero).
 */
export function Hero({
  rate,
  cleanPasses,
  completed,
  blockEligible,
  highTotal,
  mediumTotal,
  incompleteCoverage,
  scannedRecent,
  onOpen,
}: {
  rate: number
  cleanPasses: number
  completed: number
  blockEligible: number
  highTotal: number
  mediumTotal: number
  incompleteCoverage: number
  scannedRecent: number
  onOpen: () => void
}) {
  const animatedRate = useCountUp(rate)
  // HONESTY: branch on the actual count, never the ROUNDED rate — at ≥200 scans
  // with one unclean scan, Math.round rounds the rate to 100 and would claim
  // "All clean". cleanPasses is the coverage-gated flag count from derive().
  const allClean = completed > 0 && cleanPasses === completed
  const StatusIcon = completed === 0 ? Shield : allClean ? ShieldCheck : ShieldAlert
  const statusColor =
    completed === 0 ? "var(--text-muted)" : allClean ? "var(--sev-clean)" : "var(--sev-certain)"

  return (
    <button onClick={onOpen} className="wall-click wall-focus min-w-0 rounded-md text-left">
      <div className="wall-label flex items-center gap-2">
        <StatusIcon className="h-4 w-4" style={{ color: statusColor }} aria-hidden />
        Quarantine Status
      </div>
      <div
        className="wall-figure-hero mt-2"
        style={{ color: completed === 0 ? "var(--text-muted)" : allClean ? "var(--sev-clean)" : "var(--text)" }}
      >
        {completed === 0 ? "—" : `${animatedRate}%`}
      </div>
      <p className="wall-sub mt-2">
        {completed === 0
          ? "No scans yet — run your first scan to see your quarantine status."
          : allClean
            ? `All ${completed} scans came back clean.`
            : `${cleanPasses} of ${completed} scans came back clean.`}
      </p>
      {(blockEligible > 0 || highTotal > 0 || mediumTotal > 0) && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {blockEligible > 0 && (
            <span className="wall-chip" style={chipColor("var(--sev-certain)")}>
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
              {formatNumber(blockEligible)} block-eligible
            </span>
          )}
          {highTotal > 0 && (
            <span className="wall-chip" style={chipColor("var(--sev-high)")}>
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
              {formatNumber(highTotal)} high
            </span>
          )}
          {mediumTotal > 0 && (
            <span className="wall-chip" style={chipColor("var(--sev-medium)")}>
              <Info className="h-3.5 w-3.5" aria-hidden />
              {formatNumber(mediumTotal)} medium
            </span>
          )}
        </div>
      )}
      <p className="wall-sub mt-2">
        {completed} scans completed · {scannedRecent} in last 10 min
        {incompleteCoverage > 0 && (
          <span className="inline-flex items-center gap-1" style={{ color: "var(--sev-medium)" }}>
            {" · "}
            <Info className="h-3.5 w-3.5" aria-hidden />
            {incompleteCoverage} with incomplete coverage
          </span>
        )}
      </p>
    </button>
  )
}
