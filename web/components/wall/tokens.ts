/** Shared color + label maps for the Command Wall (scoped CSS vars from wall.css). */
import type { Sev } from "@/lib/useWallData"

export const SEV_COLOR: Record<Sev, string> = {
  certain: "var(--wall-sev-certain)",
  high: "var(--wall-sev-high)",
  medium: "var(--wall-sev-medium)",
  clean: "var(--wall-sev-clean)",
}

export const SEV_LABEL: Record<Sev, string> = {
  certain: "Certain",
  high: "High",
  medium: "Medium",
  clean: "Clean",
}

/** Audit action → log label + color. Color is always paired with the label text. */
export const ACTION_META: Record<string, { label: string; color: string }> = {
  "scan.created": { label: "QUEUED", color: "var(--wall-act-created)" },
  "scan.running": { label: "RUNNING", color: "var(--wall-act-running)" },
  "scan.completed": { label: "COMPLETED", color: "var(--wall-act-completed)" },
  "scan.failed": { label: "FAILED", color: "var(--wall-act-failed)" },
  "settings.updated": { label: "SETTINGS", color: "var(--wall-violet)" },
}

export function actionMeta(action: string) {
  return ACTION_META[action] ?? { label: action.toUpperCase(), color: "var(--wall-muted)" }
}
