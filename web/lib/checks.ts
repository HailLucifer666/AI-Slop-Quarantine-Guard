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
}

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
