"use client"

import { RULE_IDS, checkName } from "@/lib/checks"

// Iterates the shared rule list, so a newly registered check charts itself.
const RULES = RULE_IDS
const RULE_COLOR: Record<string, string> = {
  SQG001: "bg-sev-certain",
  SQG002: "bg-sev-certain",
  SQG003: "bg-sev-medium",
  SQG004: "bg-sev-high",
  SQG005: "bg-sev-high",
  SQG006: "bg-sev-high",
  SQG007: "bg-sev-medium",
  SQG009: "bg-sev-medium",
}

/**
 * Findings-by-check lollipop (Check-Box "product" column style): one row per
 * SQG rule, stem width ∝ count, dot at the end. Token colors only.
 */
export function LollipopChart({ byRule }: { byRule: Record<string, number> }) {
  const max = Math.max(1, ...RULES.map((id) => byRule[id] ?? 0))
  const hasData = RULES.some((id) => (byRule[id] ?? 0) > 0)

  return (
    <div className="space-y-3">
      {RULES.map((id) => {
        const v = byRule[id] ?? 0
        const pct = v === 0 ? 0 : Math.max(4, Math.round((v / max) * 100))
        const color = RULE_COLOR[id]
        return (
          <div key={id} className="grid grid-cols-[150px_1fr_28px] items-center gap-3 text-sm">
            <span className="truncate text-text-muted" title={checkName(id)}>
              {checkName(id)}
            </span>
            <div className="relative flex h-3 items-center">
              <div className="h-px w-full bg-border" />
              <div
                className={`absolute left-0 h-1 origin-left animate-lollipop-grow rounded-full ${v ? color : "bg-transparent"}`}
                style={{ width: `${pct}%` }}
              />
              {v > 0 && (
                <span
                  className={`absolute h-3 w-3 -translate-x-1/2 rounded-full ${color}`}
                  style={{ left: `${pct}%` }}
                />
              )}
            </div>
            <span className="tnum text-right text-xs text-text">{v}</span>
          </div>
        )
      })}
      {!hasData && <p className="text-center text-xs text-text-faint">No findings recorded yet</p>}
    </div>
  )
}
