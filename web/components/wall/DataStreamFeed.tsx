"use client"

import { Terminal } from "lucide-react"

import { shortRef } from "@/lib/format"
import type { AuditEntry } from "@/lib/types"

const MAX_ROWS = 30

// Real audit actions → reference-style event tokens (colored). Names are stylistic
// but each maps 1:1 to a real lifecycle action — nothing fabricated.
const TOKEN: Record<string, { name: string; color: string }> = {
  "scan.created": { name: "CreateEvent", color: "var(--wall-act-created)" },
  "scan.running": { name: "RunEvent", color: "var(--wall-act-running)" },
  "scan.completed": { name: "CompleteEvent", color: "var(--wall-act-completed)" },
  "scan.failed": { name: "FailEvent", color: "var(--wall-act-failed)" },
  "settings.updated": { name: "ConfigEvent", color: "var(--wall-violet)" },
}
function tokenOf(action: string) {
  return TOKEN[action] ?? { name: action, color: "var(--wall-muted)" }
}

function metaOf(e: AuditEntry): string {
  const d = e.details ?? {}
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

/** Reference's "Data Stream" — real-time event log, exact token format. */
export function DataStreamFeed({ feed }: { feed: AuditEntry[] }) {
  const rows = feed.slice(0, MAX_ROWS)
  const stamp = rows[0]?.created_at ? new Date(rows[0].created_at).toISOString().slice(11, 19) : "--:--:--"

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between">
        <div>
          <div className="wall-label flex items-center gap-2">
            <Terminal className="h-3.5 w-3.5" style={{ color: "var(--wall-muted)" }} aria-hidden />
            Data Stream
          </div>
          <div className="mt-1 text-[11px]" style={{ color: "var(--wall-faint)" }}>
            Real-Time
          </div>
        </div>
        <span className="wall-mono mt-0.5" style={{ color: "var(--wall-faint)" }}>
          {stamp}
        </span>
      </div>

      <div
        className="wall-scroll mt-3 min-h-0 flex-1 overflow-y-auto pr-1"
        style={{ maskImage: "linear-gradient(to bottom,#000 95%,transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom,#000 95%,transparent 100%)" }}
      >
        {rows.length === 0 ? (
          <p className="wall-mono" style={{ color: "var(--wall-faint)" }}>
            Awaiting events — run a scan to populate the stream.
          </p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {rows.map((e) => {
              const tok = tokenOf(e.action)
              const meta = metaOf(e)
              return (
                <li key={e.id} className="wall-mono">
                  <div style={{ color: "var(--wall-faint)" }}>{e.created_at ? new Date(e.created_at).toISOString() : ""}</div>
                  <div className="flex flex-wrap items-baseline gap-x-1.5">
                    <span style={{ color: "var(--wall-faint)" }}>#{e.id}</span>
                    <span style={{ color: "var(--wall-faint)" }}>:</span>
                    <span style={{ color: tok.color }}>{tok.name}</span>
                    <span style={{ color: "var(--wall-faint)" }}>→</span>
                    <span style={{ color: "var(--wall-muted)" }}>{targetOf(e)}</span>
                  </div>
                  {meta && <div style={{ color: "var(--wall-faint)" }}>{meta}</div>}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
