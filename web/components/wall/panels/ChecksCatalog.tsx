"use client"

import { CHECKS } from "@/lib/checks"

/** Checks catalog overlay — the 6 SQG checks, plain-English, severity glyph. */
const SEV: Record<string, string> = {
  SQG001: "var(--wall-sev-certain)",
  SQG002: "var(--wall-sev-certain)",
  SQG003: "var(--wall-sev-medium)",
  SQG004: "var(--wall-sev-high)",
  SQG005: "var(--wall-sev-high)",
  SQG006: "var(--wall-sev-high)",
}
// Checks that produce block-eligible (provable) findings vs advisory-only.
const BLOCKABLE = new Set(["SQG001", "SQG002"])

export function ChecksCatalog() {
  const checks = Object.values(CHECKS)
  return (
    <div className="space-y-4">
      <div className="rounded-lg p-3 text-sm" style={{ color: "var(--wall-muted)", background: "rgba(43,134,255,0.06)", border: "1px solid var(--wall-line)" }}>
        Every check runs on every scan and reports its findings. Nothing blocks today — enforcement is advisory-only until a later phase, and even then only <span style={{ color: "var(--wall-text)" }}>provable</span> findings can block.
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {checks.map((c) => {
          const blockable = BLOCKABLE.has(c.id)
          return (
            <div key={c.id} className="wall-card flex flex-col gap-2 p-5">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: SEV[c.id], boxShadow: `0 0 10px ${SEV[c.id]}` }} aria-hidden />
                <span className="font-mono text-xs" style={{ color: "var(--wall-faint)" }}>{c.id}</span>
                <span className="ml-auto rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide" style={{ color: blockable ? "var(--wall-sev-certain)" : "var(--wall-muted)", border: `1px solid ${blockable ? "var(--wall-sev-certain)" : "var(--wall-line)"}` }}>
                  {blockable ? "Can block" : "Advisory"}
                </span>
              </div>
              <div className="font-display text-base font-semibold" style={{ color: "var(--wall-text)" }}>{c.name}</div>
              <p className="text-sm" style={{ color: "var(--wall-muted)" }}>{c.blurb}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
