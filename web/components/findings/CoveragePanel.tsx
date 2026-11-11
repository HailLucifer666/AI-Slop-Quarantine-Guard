"use client"

import { AlertTriangle, CheckCircle2, CircleSlash, Clock, MinusCircle, XCircle } from "lucide-react"

import { checkName } from "@/lib/checks"
import { formatDuration } from "@/lib/format"
import type { Coverage, RuleStatus } from "@/lib/types"

/**
 * What each check actually examined — the receipt behind the headline.
 *
 * A scan that reports zero findings is only good news if the checks ran. Previously
 * "unsupported language", "timed out" and "found nothing" all rendered identically, so a
 * Go repository could show a clean result from checks that never read a single Go file.
 * This panel states, per rule: whether it ran, what it covered, and what it could not.
 */

interface StatusStyle {
  label: string
  color: string
  Icon: typeof CheckCircle2
  /** True when "found nothing" from this rule actually means something. */
  conclusive: boolean
}

const STATUS: Record<RuleStatus, StatusStyle> = {
  ran: { label: "Ran", color: "var(--wall-sev-clean)", Icon: CheckCircle2, conclusive: true },
  partial: { label: "Partial", color: "var(--wall-sev-medium)", Icon: AlertTriangle, conclusive: false },
  not_run_unsupported: { label: "Not run · unsupported", color: "var(--wall-faint)", Icon: CircleSlash, conclusive: false },
  not_run_engine_missing: { label: "Not run · engine missing", color: "var(--wall-sev-medium)", Icon: CircleSlash, conclusive: false },
  not_run_disabled: { label: "Switched off", color: "var(--wall-faint)", Icon: MinusCircle, conclusive: false },
  errored: { label: "Error", color: "var(--wall-act-failed)", Icon: XCircle, conclusive: false },
  timed_out: { label: "Timed out", color: "var(--wall-act-failed)", Icon: Clock, conclusive: false },
}

const UNKNOWN: StatusStyle = {
  label: "Unknown", color: "var(--wall-faint)", Icon: CircleSlash, conclusive: false,
}

export function CoveragePanel({ coverage }: { coverage: Coverage | null }) {
  // Scans recorded before coverage existed have none. Say that, rather than drawing an
  // empty table that implies nothing ran.
  if (!coverage || coverage.rules.length === 0) {
    return (
      <section className="wall-card p-4">
        <h3 className="wall-label">What was checked</h3>
        <p className="mt-2 text-sm" style={{ color: "var(--wall-muted)" }}>
          Coverage wasn&apos;t recorded for this scan, so we can&apos;t say which checks ran.
          Re-scan to get a full coverage report.
        </p>
      </section>
    )
  }

  const incomplete = coverage.rules_incomplete

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="wall-label">What was checked</h3>
        <span className="text-xs" style={{ color: incomplete > 0 ? "var(--wall-sev-medium)" : "var(--wall-sev-clean)" }}>
          {coverage.rules_ran} of {coverage.rules_total} checks ran
        </span>
      </div>

      {incomplete > 0 && (
        <div
          className="flex items-start gap-2 rounded-lg p-3 text-sm"
          style={{
            color: "var(--wall-muted)",
            background: "rgba(255,200,61,0.06)",
            border: "1px solid rgba(255,200,61,0.2)",
          }}
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--wall-sev-medium)" }} aria-hidden />
          <span>
            <strong style={{ color: "var(--wall-text)" }}>
              {incomplete} check{incomplete === 1 ? "" : "s"} didn&apos;t reach a conclusive result.
            </strong>{" "}
            Anything those would have caught is unknown here — not absent.
          </span>
        </div>
      )}

      <div className="space-y-2">
        {coverage.rules.map((rule) => {
          const style = STATUS[rule.status] ?? UNKNOWN
          const { Icon } = style
          return (
            <div
              key={rule.rule_id}
              className="rounded-lg p-3"
              style={{ border: "1px solid var(--wall-line)", background: "var(--wall-bg-deep)" }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Icon className="h-4 w-4 shrink-0" style={{ color: style.color }} aria-hidden />
                <span className="font-mono text-xs" style={{ color: "var(--wall-faint)" }}>{rule.rule_id}</span>
                <span className="text-sm font-medium" style={{ color: "var(--wall-text)" }}>
                  {checkName(rule.rule_id) || rule.title}
                </span>
                <span
                  className="rounded-md px-2 py-0.5 text-xs"
                  style={{ color: style.color, border: `1px solid ${style.color}`, opacity: 0.9 }}
                >
                  {style.label}
                </span>
                <span className="ml-auto flex items-center gap-3 text-xs" style={{ color: "var(--wall-faint)" }}>
                  {rule.duration_ms !== null && <span>{formatDuration(rule.duration_ms)}</span>}
                  <span className="wall-num text-sm" style={{ color: rule.findings > 0 ? "var(--wall-text)" : "var(--wall-faint)" }}>
                    {rule.findings}
                  </span>
                </span>
              </div>

              {rule.covered.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                  <span style={{ color: "var(--wall-faint)" }}>Covered:</span>
                  {rule.covered.map((item) => (
                    <span
                      key={item}
                      className="rounded px-1.5 py-0.5"
                      style={{ color: "var(--wall-muted)", background: "rgba(255,255,255,0.04)" }}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              )}

              {/* The load-bearing row: what this check could NOT see. */}
              {rule.not_covered.length > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                  <span style={{ color: "var(--wall-sev-medium)" }}>Not covered:</span>
                  {rule.not_covered.map((item) => (
                    <span
                      key={item}
                      className="rounded px-1.5 py-0.5"
                      style={{ color: "var(--wall-sev-medium)", background: "rgba(255,200,61,0.08)" }}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              )}

              {rule.detail && (
                <p className="mt-1.5 text-xs" style={{ color: "var(--wall-faint)" }}>{rule.detail}</p>
              )}

              {rule.engine && rule.engine !== "builtin" && (
                <p className="mt-1 font-mono text-[11px]" style={{ color: "var(--wall-faint)" }}>
                  {rule.engine}{rule.engine_version ? ` ${rule.engine_version}` : ""}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
