"use client"

import { CHECKS } from "@/lib/checks"

/** Checks catalog overlay — every registered SQG check, plain-English, severity glyph.
 *  The list comes from CHECKS, so it cannot fall behind the analyzers that actually run. */
const SEV_TIER: Record<string, string> = {
  SQG001: "Certain",
  SQG002: "Certain",
  SQG003: "Medium",
  SQG004: "High",
  SQG005: "High",
  SQG006: "High",
  SQG007: "Medium",
  SQG009: "Medium",
}
const SEV: Record<string, string> = {
  SQG001: "var(--sev-certain)",
  SQG002: "var(--sev-certain)",
  SQG003: "var(--sev-medium)",
  SQG004: "var(--sev-high)",
  SQG005: "var(--sev-high)",
  SQG006: "var(--sev-high)",
  SQG007: "var(--sev-medium)",
  SQG009: "var(--sev-medium)",
}
// Checks that produce block-eligible (provable) findings vs advisory-only.
const BLOCKABLE = new Set(["SQG001", "SQG002"])

export function ChecksCatalog() {
  const checks = Object.values(CHECKS)
  return (
    <div className="space-y-4">
      <div className="rounded-lg p-3 text-sm" style={{ color: "var(--text-muted)", background: "rgba(255,255,255,0.03)", border: "1px solid var(--line)" }}>
        Every check runs on every scan and reports its findings. Nothing blocks today — enforcement is advisory-only until a later phase, and even then only <span style={{ color: "var(--text)" }}>provable</span> findings can block.
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {checks.map((c) => {
          const blockable = BLOCKABLE.has(c.id)
          return (
            <div key={c.id} className="wall-card flex flex-col gap-2 p-5">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: SEV[c.id], boxShadow: `0 0 10px ${SEV[c.id]}` }} aria-hidden />
                <span className="sr-only">{`Severity tier: ${SEV_TIER[c.id] ?? "Medium"}`}</span>
                <span className="font-mono text-xs" style={{ color: "var(--text-faint)" }}>{c.id}</span>
                <span className="wall-num ml-auto rounded px-1.5 py-0.5 text-xs" style={{ color: blockable ? "var(--sev-certain)" : "var(--text-muted)", border: `1px solid ${blockable ? "var(--sev-certain)" : "var(--line)"}` }}>
                  {blockable ? "Can block" : "Advisory"}
                </span>
              </div>
              <div className="font-display text-base font-semibold" style={{ color: "var(--text)" }}>{c.name}</div>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>{c.blurb}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
