"use client"

import { useState } from "react"
import { ChevronDown, Layers } from "lucide-react"

import { checkName } from "@/lib/checks"
import { cn } from "@/lib/utils"
import type { Finding, FindingGroup, FindingGroups } from "@/lib/types"
import { FindingCard } from "./FindingCard"
import { SeverityBadge } from "./SeverityBadge"

/**
 * Findings clustered by issue, most severe first.
 *
 * A real scan produced 97 findings of which 92 were the same `innerHTML` pattern; a flat
 * severity-sorted list still buried the two HIGH findings once you scrolled, and the old
 * per-severity cap hid the tail entirely. Grouping collapses repetition — never severity,
 * and never a finding: a collapsed group always states its true occurrence count, and
 * secrets and hallucinated dependencies are deliberately never collapsed, because each
 * one is a separate incident.
 */

/** How many occurrence rows to mount at once inside an expanded group. */
const OCCURRENCE_CHUNK = 25

function GroupRow({ group }: { group: FindingGroup }) {
  const [open, setOpen] = useState(false)
  const [limit, setLimit] = useState(OCCURRENCE_CHUNK)
  const hidden = group.occurrences.length - limit
  // The payload caps occurrences; `count` is the truth. Say so rather than letting the
  // shorter list read as the whole story.
  const notInPayload = group.count - group.occurrences_shown

  return (
    <div className="wall-card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-2 p-4 text-left transition-colors hover:bg-white/[0.02] focus-visible:outline-none focus-visible:ring-2"
        style={{ ["--tw-ring-color" as string]: "var(--wall-cyan)" }}
      >
        <SeverityBadge confidence={group.confidence} />
        <span className="rounded-md px-2 py-1 font-mono text-xs" style={{ color: "var(--wall-faint)", border: "1px solid var(--wall-line)" }}>
          {group.rule_id}
        </span>
        <span className="text-sm font-medium" style={{ color: "var(--wall-text)" }}>
          {checkName(group.rule_id)}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm" style={{ color: "var(--wall-muted)" }}>
          {group.title}
        </span>
        <span className="flex shrink-0 items-center gap-2 text-xs" style={{ color: "var(--wall-muted)" }}>
          <Layers className="h-3.5 w-3.5" aria-hidden />
          <span className="wall-num">{group.count}</span>
          <span style={{ color: "var(--wall-faint)" }}>
            in {group.file_count} file{group.file_count === 1 ? "" : "s"}
          </span>
          <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />
        </span>
      </button>

      {open && (
        <div className="border-t px-4 pb-4 pt-3" style={{ borderColor: "var(--wall-line)" }}>
          <ul className="space-y-1.5">
            {group.occurrences.slice(0, limit).map((o) => (
              <li key={o.fingerprint + o.line_start} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
                <span className="font-mono" style={{ color: "var(--wall-cyan)" }}>
                  {o.file_path}:{o.line_start}
                </span>
                {o.snippet && (
                  <code className="min-w-0 flex-1 truncate rounded px-1.5 py-0.5 font-mono" style={{ color: "var(--wall-muted)", background: "rgba(255,255,255,0.04)" }}>
                    {o.snippet}
                  </code>
                )}
              </li>
            ))}
          </ul>

          {hidden > 0 && (
            <button
              onClick={() => setLimit((l) => l + OCCURRENCE_CHUNK)}
              className="wall-cta-secondary mt-3 inline-flex w-auto items-center gap-2 text-xs"
            >
              Show {Math.min(hidden, OCCURRENCE_CHUNK)} more · {hidden} hidden
            </button>
          )}

          {notInPayload > 0 && (
            <p className="mt-3 text-xs" style={{ color: "var(--wall-faint)" }}>
              Showing {group.occurrences_shown} of {group.count} occurrences. The rest are counted
              but not listed here — open the full findings list below to see every one.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function GroupedFindings({
  groups,
  findings,
}: {
  groups: FindingGroups | null
  findings: Finding[]
}) {
  if (!groups || groups.groups.length === 0) return null

  // Non-collapsed issues get the full finding card (advisories, remediation, evidence).
  // The group payload carries only locations, so look the finding back up by fingerprint.
  const byFingerprint = new Map(findings.map((f) => [f.fingerprint, f]))

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="wall-label">Issues found</h3>
        <span className="text-xs" style={{ color: "var(--wall-faint)" }}>
          {groups.groups_total} distinct issue{groups.groups_total === 1 ? "" : "s"} ·{" "}
          {groups.findings_total} finding{groups.findings_total === 1 ? "" : "s"}
          {groups.collapsed_groups > 0 && ` · ${groups.collapsed_groups} grouped`}
        </span>
      </div>

      {groups.groups.map((group) => {
        if (group.grouped) return <GroupRow key={group.key} group={group} />

        // A discrete incident: render every occurrence as its own full card.
        return (
          <div key={group.key} className="space-y-3">
            {group.occurrences.map((o) => {
              const finding = byFingerprint.get(o.fingerprint)
              return finding ? (
                <FindingCard key={o.fingerprint} finding={finding} />
              ) : (
                // Fingerprint mismatch (e.g. an older stored scan). Show the location we
                // do have rather than dropping the finding from the view entirely.
                <div key={o.fingerprint + o.line_start} className="wall-card p-4 text-sm" style={{ color: "var(--wall-muted)" }}>
                  <span className="font-mono text-xs" style={{ color: "var(--wall-cyan)" }}>
                    {o.file_path}:{o.line_start}
                  </span>
                  <p className="mt-1">{group.title}</p>
                </div>
              )
            })}
          </div>
        )
      })}
    </section>
  )
}
