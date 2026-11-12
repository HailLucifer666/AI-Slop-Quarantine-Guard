/** Shared color + label maps for the Command Wall.
 *
 * CSS-var colors come from the merged token system (wall.css :root, mirrored in
 * web/DESIGN.md). SEV_HEX is the ONE JS-side hex source for canvas / three.js —
 * CSS vars can't feed WebGL — and must stay value-identical to the --sev-* vars.
 * Icon/label canonical source: lib/severity.ts (SEV_ICON maps its names to the
 * lucide components). */
import { ShieldAlert, AlertTriangle, Info, ShieldCheck } from "lucide-react"
import type { LucideIcon } from "lucide-react"

import type { Sev } from "@/lib/useWallData"

export const SEV_COLOR: Record<Sev, string> = {
  certain: "var(--sev-certain)",
  high: "var(--sev-high)",
  medium: "var(--sev-medium)",
  clean: "var(--sev-clean)",
}

export const SEV_HEX: Record<Sev, string> = {
  certain: "#FF3B5C",
  high: "#FF8A3D",
  medium: "#FFC83D",
  clean: "#2DE08A",
}

export const SEV_LABEL: Record<Sev, string> = {
  certain: "Certain",
  high: "High",
  medium: "Medium",
  clean: "Clean",
}

/** Severity is never color-only: icon + text + color on every chip/badge/dot. */
export const SEV_ICON: Record<Sev, LucideIcon> = {
  certain: ShieldAlert,
  high: AlertTriangle,
  medium: Info,
  clean: ShieldCheck,
}

/** Audit action → log label + color. Color is always paired with the label text. */
export const ACTION_META: Record<string, { label: string; color: string }> = {
  "scan.created": { label: "QUEUED", color: "var(--act-queued)" },
  "scan.running": { label: "RUNNING", color: "var(--act-running)" },
  "scan.completed": { label: "COMPLETED", color: "var(--act-completed)" },
  "scan.failed": { label: "FAILED", color: "var(--act-failed)" },
  "settings.updated": { label: "SETTINGS", color: "var(--accent-violet)" },
}

export function actionMeta(action: string) {
  return ACTION_META[action] ?? { label: action.toUpperCase(), color: "var(--text-muted)" }
}
