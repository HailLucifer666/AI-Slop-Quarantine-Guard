import { CheckCircle2, Clock, Loader2, ShieldAlert, XCircle } from "lucide-react"
import type { ScanStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

/**
 * Scan lifecycle status chip — icon + text + color, never color-only, styled
 * as the shared `.wall-chip`. Colors: running = cyan (liveness), failed = the
 * risk crimson, clean = severity-clean green, findings = severity-high amber,
 * queued = neutral. `clean` distinguishes completed-with-findings from all-clear.
 */
const MAP: Record<
  "queued" | "running" | "failed" | "clean" | "findings",
  { icon: typeof Clock; color: string; label: string; spin: boolean }
> = {
  queued: { icon: Clock, color: "var(--text-muted)", label: "Queued", spin: false },
  running: { icon: Loader2, color: "var(--act-running)", label: "Scanning", spin: true },
  failed: { icon: XCircle, color: "var(--sev-certain)", label: "Failed", spin: false },
  clean: { icon: CheckCircle2, color: "var(--sev-clean)", label: "All clear", spin: false },
  findings: { icon: ShieldAlert, color: "var(--sev-high)", label: "Findings", spin: false },
}

export function StatusBadge({
  status,
  clean,
  className,
}: {
  status: ScanStatus
  clean?: boolean
  className?: string
}) {
  const key = status === "completed" ? (clean ? "clean" : "findings") : status
  const map = MAP[key]
  const Icon = map.icon
  return (
    <span className={cn("wall-chip", className)} style={{ ["--chip-color" as string]: map.color }}>
      <Icon className={cn("h-3.5 w-3.5", map.spin && "animate-spin")} aria-hidden />
      {map.label}
    </span>
  )
}
