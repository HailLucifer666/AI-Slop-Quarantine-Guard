"use client"

import { useState } from "react"
import { ChevronDown, Lightbulb, Loader2, Sparkles } from "lucide-react"
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
    <div className="glass rounded-lg p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge confidence={finding.confidence} />
        <span className="rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs text-text-muted">
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
          className="mt-3 inline-flex items-center gap-1 text-xs text-text-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo"
        >
          <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />
          {open ? "Hide" : "Show"} evidence
        </button>
      )}

      {open && (
        <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-bg p-3 font-mono text-xs leading-relaxed">
          {ev.context_before.map((l, i) => (
            <div key={`b${i}`} className="text-text-faint">{l}</div>
          ))}
          <div className="bg-sev-certain/15 text-text">{ev.snippet}</div>
          {ev.context_after.map((l, i) => (
            <div key={`a${i}`} className="text-text-faint">{l}</div>
          ))}
        </pre>
      )}

      {finding.fix_suggestion && (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-brand-teal/30 bg-brand-teal/5 p-3 text-sm text-text-muted">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-brand-teal" aria-hidden />
          <span>{finding.fix_suggestion}</span>
        </div>
      )}

      {/* The Crew — advisory AI explainer (Phase 7) */}
      {!exp && (
        <button
          onClick={explain}
          disabled={loadingExp}
          className="mt-3 inline-flex items-center gap-2 rounded-md border border-brand-indigo/40 bg-brand-indigo/10 px-3 py-1.5 text-xs font-medium text-text transition-colors hover:bg-brand-indigo/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo disabled:opacity-60"
        >
          {loadingExp ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Explaining…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5 text-brand-teal" aria-hidden />
              Explain in plain English
            </>
          )}
        </button>
      )}

      {expError && <p className="mt-2 text-xs text-sev-medium">{expError}</p>}

      {exp && (
        <div className="mt-3 space-y-2 rounded-md border border-brand-indigo/30 bg-brand-indigo/5 p-3 text-sm">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand-teal">
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
          <p className="pt-1 text-[11px] text-text-faint">
            AI-generated guidance — it never changes the Guard&apos;s verdict.
          </p>
        </div>
      )}

      <div className="sr-only">{CHECKS[finding.rule_id]?.blurb}</div>
    </div>
  )
}
