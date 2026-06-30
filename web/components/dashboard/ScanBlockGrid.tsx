import Link from "next/link"
import { StatusBadge } from "@/components/findings/StatusBadge"
import { formatRelativeTime, shortRef } from "@/lib/format"
import type { ScanSummary } from "@/lib/types"

const GRID = 49 // 7×7 contribution-style grid

/**
 * Per-scan "commit blocks" card (nixtio ongoing-calls style): a 7×7 dot grid
 * where each filled dot is a finding colored by confidence; empty cells stay
 * dim. Clickable through to the scan detail.
 */
export function ScanBlockGrid({ scan }: { scan: ScanSummary }) {
  const a = scan.analytics
  const certain = a?.by_confidence?.CERTAIN ?? 0
  const high = a?.by_confidence?.HIGH ?? 0
  const medium = a?.by_confidence?.MEDIUM ?? 0
  const total = a?.total_findings ?? 0

  const filled = [
    ...Array(certain).fill("bg-sev-certain"),
    ...Array(high).fill("bg-sev-high"),
    ...Array(medium).fill("bg-sev-medium"),
  ].slice(0, GRID)
  const cells = [...filled, ...Array(Math.max(0, GRID - filled.length)).fill("bg-surface-elevated")]

  return (
    <Link
      href={`/analyses/${scan.id}`}
      className="glass block rounded-lg p-4 transition-transform hover:-translate-y-0.5"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-text" title={scan.ref}>
            {shortRef(scan.ref)}
          </div>
          <div className="text-xs text-text-faint">{formatRelativeTime(scan.created_at)}</div>
        </div>
        <StatusBadge status={scan.status} clean={a?.clean} />
      </div>

      <div className="mt-3 grid grid-cols-[repeat(7,1fr)] gap-1.5">
        {cells.map((c, i) => (
          <span
            key={i}
            className={`aspect-square rounded-[3px] ${c} ${filled[i] ? "animate-dot-reveal" : ""}`}
            style={filled[i] ? { animationDelay: `${i * 12}ms` } : undefined}
          />
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-text-muted">
          {total === 0 ? (scan.status === "completed" ? "Clean" : "—") : `${total} finding${total === 1 ? "" : "s"}`}
        </span>
        <span className="tnum text-text-faint">{scan.files_scanned} files</span>
      </div>
    </Link>
  )
}
