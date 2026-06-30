import { AlertOctagon, AlertTriangle, Info } from "lucide-react"
import type { Confidence } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Severity is never color-only — always icon + text + color (a11y floor). */
const MAP: Record<Confidence, { icon: typeof Info; cls: string; label: string }> = {
  CERTAIN: { icon: AlertOctagon, cls: "text-sev-certain border-sev-certain/40 bg-sev-certain/10", label: "CERTAIN" },
  HIGH: { icon: AlertTriangle, cls: "text-sev-high border-sev-high/40 bg-sev-high/10", label: "HIGH" },
  MEDIUM: { icon: Info, cls: "text-sev-medium border-sev-medium/40 bg-sev-medium/10", label: "MEDIUM" },
}

export function SeverityBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  const { icon: Icon, cls, label } = MAP[confidence] ?? MAP.MEDIUM
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs", cls, className)}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </span>
  )
}
