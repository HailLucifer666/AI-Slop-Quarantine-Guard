/** SQG check catalog — plain-English metadata for non-technical users. */
import type { Confidence } from "./types"
import type { SeverityKey } from "./severity"

export interface CheckMeta {
  id: string
  name: string
  blurb: string
  /** True only for SQG001/SQG002 — the two rules whose CERTAIN findings may block (G2). */
  blockEligible: boolean
  /** This rule's typical severity tier — the ONE color axis for per-check UI
   * (charts, dots). Never a second, unrelated color palette (see severity.ts). */
  severity: SeverityKey
}

export const CHECKS: Record<string, CheckMeta> = {
  SQG001: { id: "SQG001", name: "Hallucinated package", blurb: "A dependency that doesn't exist in its registry — a classic AI invention.", blockEligible: true, severity: "certain" },
  SQG002: { id: "SQG002", name: "Leaked secret", blurb: "An API key, token, or password committed into the code.", blockEligible: true, severity: "certain" },
  SQG003: { id: "SQG003", name: "Placeholder code", blurb: "TODO/FIXME or unimplemented stubs left behind.", blockEligible: false, severity: "medium" },
  SQG004: { id: "SQG004", name: "Vulnerable dependency", blurb: "A package version with a known security advisory (CVE).", blockEligible: false, severity: "high" },
  SQG005: { id: "SQG005", name: "Risky license", blurb: "A dependency whose license may conflict with your project.", blockEligible: false, severity: "high" },
  SQG006: { id: "SQG006", name: "Security issue", blurb: "A potentially dangerous code pattern flagged by static analysis.", blockEligible: false, severity: "high" },
  SQG007: { id: "SQG007", name: "Possible typosquat", blurb: "A dependency whose name closely resembles a popular package — verify it's the one you meant. Advisory only.", blockEligible: false, severity: "medium" },
  // SQG008 is specified but not built, so it is deliberately absent rather than shown
  // as a check that always finds nothing.
  SQG009: { id: "SQG009", name: "Longer than it needs to be", blurb: "Several lines of code that one equivalent line replaces. Each finding shows the shorter version, worked out from the code itself. Python only, advisory.", blockEligible: false, severity: "medium" },
}

/**
 * Every implemented rule, in display order — the ONE list the UI iterates.
 *
 * Six components used to hardcode their own `["SQG001" … "SQG006"]`, so adding SQG007
 * left typosquat findings counted by the backend and invisible in every chart. Deriving
 * from CHECKS means a new rule appears everywhere the moment it is registered above,
 * instead of silently vanishing from whichever list nobody remembered to update.
 */
export const RULE_IDS: string[] = Object.keys(CHECKS)

export function checkName(ruleId: string): string {
  return CHECKS[ruleId]?.name ?? ruleId
}

/** Confidence → plain-English meaning. */
export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  CERTAIN: "Proven fact",
  HIGH: "Likely",
  MEDIUM: "Worth a look",
}

export const CONFIDENCE_ORDER: Confidence[] = ["CERTAIN", "HIGH", "MEDIUM"]
