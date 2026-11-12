"use client"

import { useState } from "react"
import { Terminal } from "lucide-react"

import { shortRef } from "@/lib/format"
import type { AuditEntry } from "@/lib/types"
import { cn } from "@/lib/utils"

const MAX_ROWS = 30

/**
 * Data Stream (spec §4) — the real-time audit log. Filter chips (All / Failed /
 * Block-eligible) over REAL fields only, plain-English event names (one per real
 * action — unknown actions render the raw action string, never an invention),
 * 12px mono floor, severity dot + readable name (never color-only).
 */

// Real audit actions → plain names (extend this map only with real actions).
const TOKEN: Record<string, { name: string; color: string }> = {
  "scan.created": { name: "scan created", color: "var(--act-queued)" },
  "scan.running": { name: "scan running", color: "var(--act-running)" },
  "scan.completed": { name: "scan completed", color: "var(--act-completed)" },
  "scan.failed": { name: "scan failed", color: "var(--act-failed)" },
  "scan.shadow_block": { name: "shadow block", color: "var(--sev-certain)" },
  "settings.updated": { name: "settings updated", color: "var(--accent-violet)" },
}
function tokenOf(action: string) {
  return TOKEN[action] ?? { name: action, color: "var(--text-muted)" }
}

function metaOf(e: AuditEntry): string {
  const d = e.details ?? {}
  // scan.shadow_block payload: { scan_id, would_block, note } (api/app/store.py).
  if (e.action === "scan.shadow_block") {
    return `would block ${Number(d.would_block ?? 0)} · shadow only`
  }
  const parts: string[] = []
  if (typeof d.total_findings === "number") parts.push(`findings — ${d.total_findings}`)
  if (typeof d.reason === "string") parts.push(d.reason)
  if (typeof d.retention_days === "number") parts.push(`retain ${d.retention_days}d`)
  return parts.join("  ")
}
function targetOf(e: AuditEntry): string {
  const d = e.details ?? {}
  if (typeof d.ref === "string") return shortRef(d.ref)
  if (typeof d.scan_id === "number") return `scan/${d.scan_id}`
  return "—"
}

type FilterKey = "all" | "failed" | "block"
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "failed", label: "Failed" },
  { key: "block", label: "Block-eligible" },
]
// Filter semantics over real fields only: the scan.completed audit payload
// carries block_eligible (api/app/store.py complete_scan()).
function matches(f: FilterKey, e: AuditEntry): boolean {
  if (f === "all") return true
  if (f === "failed") return e.action === "scan.failed"
  return e.action === "scan.completed" && Number(e.details?.block_eligible ?? 0) > 0
}

/** Reference's "Data Stream" — real-time event log with honest filters. */
export function DataStreamFeed({ feed }: { feed: AuditEntry[] }) {
  const [filter, setFilter] = useState<FilterKey>("all")

  const filtered = feed.filter((e) => matches(filter, e))
  const rows = filtered.slice(0, MAX_ROWS)
  const stamp = rows[0]?.created_at ? new Date(rows[0].created_at).toISOString().slice(11, 19) : "--:--:--"

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between">
        <div>
          <div className="wall-label flex items-center gap-2">
            <Terminal className="h-3.5 w-3.5" style={{ color: "var(--text-muted)" }} aria-hidden />
            Data Stream
          </div>
          <div className="wall-sub mt-1">Real-Time</div>
        </div>
        <span className="wall-mono mt-0.5" style={{ color: "var(--text-faint)" }}>
          {stamp}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2" role="group" aria-label="Stream filters">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
            className={cn("wall-filter wall-focus", filter === f.key && "wall-filter-on")}
          >
            {f.label}
          </button>
        ))}
      </div>
      <p className="wall-sub mt-1" aria-live="polite">
        {filtered.length} events
      </p>

      <div
        className="wall-scroll mt-2 min-h-0 flex-1 overflow-y-auto pr-1"
        style={{ maskImage: "linear-gradient(to bottom,#000 95%,transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom,#000 95%,transparent 100%)" }}
      >
        {rows.length === 0 ? (
          <p className="wall-mono" style={{ color: "var(--text-faint)" }}>
            {feed.length === 0
              ? "Awaiting events — run a scan to populate the stream."
              : "No matching events in the current stream."}
          </p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {rows.map((e) => {
              const tok = tokenOf(e.action)
              const meta = metaOf(e)
              return (
                <li key={e.id} className="wall-mono">
                  <div className="flex flex-wrap items-center gap-x-1.5">
                    <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: tok.color }} />
                    <span style={{ color: tok.color }}>{tok.name}</span>
                    <span style={{ color: "var(--text-faint)" }}>→</span>
                    <span style={{ color: "var(--text-muted)" }}>{targetOf(e)}</span>
                    <span style={{ color: "var(--text-faint)" }}>#{e.id}</span>
                  </div>
                  {/* Full ISO timestamp — real and unambiguous. */}
                  <div style={{ color: "var(--text-faint)" }}>
                    {e.created_at ? new Date(e.created_at).toISOString() : ""}
                  </div>
                  {meta && <div style={{ color: "var(--text-faint)" }}>{meta}</div>}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
