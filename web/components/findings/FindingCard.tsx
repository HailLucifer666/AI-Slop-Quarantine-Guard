"use client"

import { useState } from "react"
import { ChevronDown, Lightbulb, Loader2, Sparkles, Wrench } from "lucide-react"
import type { Explanation, Finding } from "@/lib/types"
import { checkName, CHECKS } from "@/lib/checks"
import { explainFinding } from "@/lib/api"
import { cn } from "@/lib/utils"
import { SeverityBadge } from "./SeverityBadge"

export function FindingCard({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false)
  const [exp, setExp] = useState<Explanation | null>(null)
  const [loadingExp, setLoadingExp] = useState(false)
  const [expError, setExpError] = useState<string | null>(null)
  const ev = finding.evidence
  // Findings stored before cwe/advisories shipped have neither key (historical rows
  // are rendered as-is). Absent means "no references were stated" — render nothing,
  // never crash on history.
  const cwe = finding.cwe ?? []
  const advisories = finding.advisories ?? []

  async function explain() {
    if (exp || loadingExp) return
    setLoadingExp(true)
    setExpError(null)
    try {
      setExp(await explainFinding(finding))
    } catch (e) {
      setExpError(e instanceof Error ? e.message : "Explanation unavailable right now.")
    } finally {
      setLoadingExp(false)
    }
  }

  return (
    <div className="wall-card rounded-lg p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge confidence={finding.confidence} />
        <span className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs text-text-muted">
          {finding.rule_id}
        </span>
        <span className="text-sm font-medium text-text">{checkName(finding.rule_id)}</span>
        {finding.block_eligible && (
          <span
            className="rounded-md border border-sev-certain/40 bg-sev-certain/10 px-2 py-0.5 text-xs text-sev-certain"
            title="A provable fact — this is the kind of finding that would block a merge once enforcement is enabled. Everything without this tag is advisory."
          >
            block-eligible
          </span>
        )}
      </div>

      <p className="mt-3 text-sm text-text-muted">{finding.message}</p>

      <div className="mt-2 font-mono text-xs text-text-faint">
        {finding.file_path}:{finding.line_start}
        {finding.line_end !== finding.line_start ? `-${finding.line_end}` : ""}
      </div>

      {(ev.snippet || ev.context_before.length || ev.context_after.length) && (
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="mt-3 inline-flex items-center gap-1 text-xs text-text-muted hover:text-text wall-focus"
        >
          <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />
          {open ? "Hide" : "Show"} evidence
        </button>
      )}

      {open && (
        <pre className="mt-2 overflow-x-auto rounded-md border border-line bg-bg p-3 font-mono text-xs leading-relaxed">
          {ev.context_before.map((l, i) => (
            <div key={`b${i}`} className="text-text-faint">{l}</div>
          ))}
          <div className="bg-sev-certain/15 text-text">{ev.snippet}</div>
          {ev.context_after.map((l, i) => (
            <div key={`a${i}`} className="text-text-faint">{l}</div>
          ))}
        </pre>
      )}

      {/* References — CWE and published advisories as real links, so every claim the
          finding makes is checkable against a source rather than taken on trust. */}
      {(cwe.length > 0 || advisories.length > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-text-faint">References:</span>
          {cwe.map((id) => (
            <a
              key={id}
              href={`https://cwe.mitre.org/data/definitions/${id.split("-").pop()}.html`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-line bg-surface px-2 py-0.5 font-mono text-xs text-text-muted transition-colors hover:text-text wall-focus"
            >
              {id}
            </a>
          ))}
          {advisories.map((a) => (
            <a
              key={a.id}
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-sev-high/40 bg-sev-high/10 px-2 py-0.5 font-mono text-xs text-sev-high transition-opacity hover:opacity-80 wall-focus"
            >
              {a.id}
            </a>
          ))}
          {finding.severity && (
            <span className="rounded-md border border-line px-2 py-0.5 text-xs text-text-muted" title="Severity as reported by the advisory source — not computed by us.">
              {finding.severity}
            </span>
          )}
        </div>
      )}

      {/* Remediation. A concrete replacement is shown as a diff ONLY when it was derived
          mechanically from a named fixed version; anything else is prose that says so. */}
      {finding.remediation?.applicable && finding.remediation.suggested_replacement ? (
        <div className="mt-3 rounded-md border border-accent-cyan/30 bg-accent-cyan/5 p-3">
          <div className="flex items-start gap-2 text-sm text-text">
            <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-accent-cyan" aria-hidden />
            <span>{finding.remediation.text}</span>
          </div>
          <pre className="mt-2 overflow-x-auto rounded border border-line bg-bg p-2 font-mono text-xs">
            <div className="text-sev-high">- {ev.snippet}</div>
            <div className="text-accent-cyan">+ {finding.remediation.suggested_replacement}</div>
          </pre>
          {finding.remediation.basis && (
            <p className="mt-2 text-xs text-text-faint">Basis: {finding.remediation.basis}.</p>
          )}
        </div>
      ) : finding.remediation ? (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-line bg-surface p-3 text-sm text-text-muted">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-accent-cyan" aria-hidden />
          <span>
            {finding.remediation.text}
            {finding.remediation.basis && (
              <span className="mt-1 block text-xs text-text-faint">
                No automatic fix offered: {finding.remediation.basis}.
              </span>
            )}
          </span>
        </div>
      ) : finding.fix_suggestion ? (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-accent-cyan/30 bg-accent-cyan/5 p-3 text-sm text-text-muted">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-accent-cyan" aria-hidden />
          <span>{finding.fix_suggestion}</span>
        </div>
      ) : null}

      {/* The Crew — advisory AI explainer (Phase 7) */}
      {!exp && (
        <button
          onClick={explain}
          disabled={loadingExp}
          className="mt-3 inline-flex items-center gap-2 rounded-md border border-accent-violet/40 bg-accent-violet/10 px-3 py-1.5 text-xs font-medium text-text transition-colors hover:bg-accent-violet/20 wall-focus disabled:opacity-60"
        >
          {loadingExp ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Explaining…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5 text-accent-cyan" aria-hidden />
              Explain in plain English
            </>
          )}
        </button>
      )}

      {expError && <p className="mt-2 text-xs text-sev-medium">{expError}</p>}

      {exp && (
        <div className="mt-3 space-y-2 rounded-md border border-accent-violet/30 bg-accent-violet/5 p-3 text-sm">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-accent-cyan">
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            The Crew · advisory
          </div>
          {exp.explanation && <p className="text-text">{exp.explanation}</p>}
          {exp.why_it_matters && (
            <p className="text-text-muted">
              <span className="font-medium text-text">Why it matters: </span>
              {exp.why_it_matters}
            </p>
          )}
          {exp.how_to_fix && (
            <p className="whitespace-pre-line text-text-muted">
              <span className="font-medium text-text">How to fix: </span>
              {exp.how_to_fix}
            </p>
          )}
          <p className="pt-1 text-xs text-text-faint">
            AI-generated guidance — it never changes the Guard&apos;s verdict.
          </p>
        </div>
      )}

      {/* Provenance — which detector and rule revision produced this. A finding a reader
          cannot trace back to its source is a claim, not a result. */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line pt-2 font-mono text-xs text-text-faint">
        <span>
          via {finding.tool || "builtin"}
          {finding.tool_version ? ` ${finding.tool_version}` : ""}
        </span>
        {finding.rule_version && <span>rules v{finding.rule_version}</span>}
        {finding.fingerprint && <span title="Content-derived id — stable across scans and line moves.">#{finding.fingerprint}</span>}
      </div>

      <div className="sr-only">{CHECKS[finding.rule_id]?.blurb}</div>
    </div>
  )
}
