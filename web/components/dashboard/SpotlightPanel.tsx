import Link from "next/link"
import { FileCode2, ShieldAlert, Timer } from "lucide-react"
import { StatusBadge } from "@/components/findings/StatusBadge"
import { formatDuration, formatNumber, shortRef } from "@/lib/format"
import type { ScanSummary } from "@/lib/types"

/**
 * Latest-scan spotlight (Stakent "active stake" panel style): big headline
 * number + metric tiles for the most recent scan. Empty state when no scans.
 */
export function SpotlightPanel({ scan }: { scan: ScanSummary | null }) {
  if (!scan) {
    return (
      <div className="glass flex h-full flex-col items-start justify-center gap-2 rounded-lg p-6">
        <h2 className="font-display text-sm font-bold uppercase tracking-wide text-text-muted">
          Latest scan
        </h2>
        <p className="text-sm text-text-faint">Run your first scan to see it spotlighted here.</p>
        <Link href="/scan" className="text-sm text-brand-teal hover:underline">
          Start a scan →
        </Link>
      </div>
    )
  }

  const a = scan.analytics
  const clean = a?.clean ?? false
  const headline = clean ? "Clean" : formatNumber(a?.total_findings ?? 0)

  const tiles = [
    { icon: FileCode2, label: "Files", value: formatNumber(scan.files_scanned) },
    { icon: ShieldAlert, label: "Block-eligible", value: formatNumber(a?.block_eligible ?? 0) },
    { icon: Timer, label: "Duration", value: formatDuration(scan.duration_ms) },
  ]

  return (
    <div className="glass flex h-full flex-col rounded-lg p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-sm font-bold uppercase tracking-wide text-text-muted">
            Latest scan
          </h2>
          <p className="mt-0.5 truncate font-mono text-xs text-text-faint">{shortRef(scan.ref)}</p>
        </div>
        <StatusBadge status={scan.status} clean={clean} />
      </div>

      <div className="mt-4 flex items-baseline gap-2">
        <span className={`tnum text-3xl font-bold ${clean ? "text-sev-clean" : "text-text"}`}>
          {headline}
        </span>
        {!clean && <span className="text-sm text-text-muted">findings</span>}
      </div>

      <div className="mt-auto grid grid-cols-3 gap-3 pt-5">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-md border border-border bg-surface/60 p-3">
            <t.icon className="h-4 w-4 text-brand-teal" aria-hidden />
            <div className="tnum mt-2 text-lg font-semibold text-text">{t.value}</div>
            <div className="text-xs text-text-faint">{t.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
