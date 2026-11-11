/** The ONE severity color/label/icon source for the whole app. Colors reference the
 * Aurora CSS vars (app/globals.css) — never hardcode hex here or anywhere that imports this. */
import type { Confidence } from "./types"

export type SeverityKey = "certain" | "high" | "medium" | "clean"

export const SEVERITY: Record<SeverityKey, { color: string; label: string; icon: string }> = {
  certain: { color: "var(--sev-certain)", label: "Certain", icon: "ShieldAlert" },
  high: { color: "var(--sev-high)", label: "High", icon: "AlertTriangle" },
  medium: { color: "var(--sev-medium)", label: "Medium", icon: "Info" },
  clean: { color: "var(--sev-clean)", label: "Clean", icon: "ShieldCheck" },
}

/** Map a finding's confidence + block-eligibility to the severity key that drives color/icon. */
export function severityFor(confidence: Confidence, blockEligible: boolean): SeverityKey {
  if (blockEligible || confidence === "CERTAIN") return "certain"
  if (confidence === "HIGH") return "high"
  return "medium"
}
