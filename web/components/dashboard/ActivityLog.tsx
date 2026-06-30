"use client"

import { useEffect, useState } from "react"
import { Activity, ChevronDown } from "lucide-react"

import { listAudit } from "@/lib/api"
import { formatRelativeTime } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AuditEntry } from "@/lib/types"

/**
 * Collapsible audit-trail view (surfaces GET /api/audit). The Guard records every
 * scan lifecycle transition + settings change; this is the human-readable trail.
 * Lazy: only fetches once the section is opened.
 */
const LABELS: Record<string, { text: string; tone: string }> = {
  "scan.created": { text: "Scan queued", tone: "text-text-muted" },
  "scan.running": { text: "Scan started", tone: "text-scan" },
  "scan.completed": { text: "Scan completed", tone: "text-sev-clean" },
  "scan.failed": { text: "Scan failed", tone: "text-sev-certain" },
  "settings.updated": { text: "Settings updated", tone: "text-brand-teal" },
}

function detailLine(e: AuditEntry): string {
  const d = e.details ?? {}
  const parts: string[] = []
  if (typeof d.scan_id === "number") parts.push(`#${d.scan_id}`)
  if (typeof d.total_findings === "number") parts.push(`${d.total_findings} findings`)
  if (typeof d.reason === "string") parts.push(d.reason)
  if (typeof d.retention_days === "number") parts.push(`retain ${d.retention_days}d`)
  return parts.join(" · ")
}

export function ActivityLog() {
  const [open, setOpen] = useState(false)
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || entries || error) return
    listAudit()
      .then(setEntries)
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load activity."))
  }, [open, entries, error])

  return (
    <section className="glass rounded-lg p-5">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo"
      >
        <span className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide text-text-muted">
          <Activity className="h-4 w-4 text-brand-teal" aria-hidden />
          Activity
        </span>
        <ChevronDown className={cn("h-4 w-4 text-text-faint transition-transform", open && "rotate-180")} aria-hidden />
      </button>

      {open && (
        <div className="mt-4">
          {error && <p className="text-sm text-sev-certain">{error}</p>}
          {!error && entries === null && <p className="text-sm text-text-faint">Loading…</p>}
          {entries && entries.length === 0 && (
            <p className="text-sm text-text-faint">No activity recorded yet.</p>
          )}
          {entries && entries.length > 0 && (
            <ul className="space-y-2">
              {entries.map((e) => {
                const meta = LABELS[e.action] ?? { text: e.action, tone: "text-text-muted" }
                const detail = detailLine(e)
                return (
                  <li
                    key={e.id}
                    className="flex items-center justify-between gap-3 border-b border-border/50 pb-2 text-sm last:border-0 last:pb-0"
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <span className={cn("font-medium", meta.tone)}>{meta.text}</span>
                      {detail && <span className="text-text-faint">{detail}</span>}
                    </span>
                    <span className="shrink-0 text-xs text-text-faint">{formatRelativeTime(e.created_at)}</span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
