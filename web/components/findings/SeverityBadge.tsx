import { AlertTriangle, Info, ShieldAlert, ShieldCheck } from "lucide-react"
import type { Confidence } from "@/lib/types"
import { SEVERITY, severityFor, type SeverityKey } from "@/lib/severity"
import { cn } from "@/lib/utils"

/** Icon per severity key — the lucide component for the name lib/severity declares. */
const ICONS: Record<SeverityKey, typeof Info> = {
  certain: ShieldAlert,
  high: AlertTriangle,
  medium: Info,
  clean: ShieldCheck,
}

/**
 * Severity chip — icon + text + color, never color-only. Colors/labels/icons
 * come from lib/severity.ts (the one severity source); styling is the shared
 * `.wall-chip` pill with `--chip-color` set per instance.
 */
export function SeverityBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  const key = severityFor(confidence, false)
  const { color, label } = SEVERITY[key]
  const Icon = ICONS[key]
  return (
    <span
      className={cn("wall-chip", className)}
      style={{ ["--chip-color" as string]: color }}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </span>
  )
}
