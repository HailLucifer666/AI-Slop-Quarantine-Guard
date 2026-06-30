import { CheckCircle2, Clock, Loader2, ShieldAlert, XCircle } from "lucide-react"
import type { ScanStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Scan lifecycle status. `clean` distinguishes a completed-with-findings from all-clear. */
export function StatusBadge({
  status,
  clean,
  className,
}: {
  status: ScanStatus
  clean?: boolean
  className?: string
}) {
  const map = {
    queued: { icon: Clock, cls: "text-text-muted border-border bg-surface", label: "Queued", spin: false },
    running: { icon: Loader2, cls: "text-scan border-scan/40 bg-scan/10", label: "Scanning", spin: true },
    failed: { icon: XCircle, cls: "text-sev-certain border-sev-certain/40 bg-sev-certain/10", label: "Failed", spin: false },
    completed: clean
      ? { icon: CheckCircle2, cls: "text-sev-clean border-sev-clean/40 bg-sev-clean/10", label: "All clear", spin: false }
      : { icon: ShieldAlert, cls: "text-sev-high border-sev-high/40 bg-sev-high/10", label: "Findings", spin: false },
  }[status]

  const Icon = map.icon
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium", map.cls, className)}>
      <Icon className={cn("h-3.5 w-3.5", map.spin && "animate-spin")} aria-hidden />
      {map.label}
    </span>
  )
}
