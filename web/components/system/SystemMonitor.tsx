"use client"

import { useState } from "react"
import { Activity, ChevronDown } from "lucide-react"
import { MiniSparkline } from "@/components/charts/MiniSparkline"
import type { ScanSummary } from "@/lib/types"

/**
 * Floating scan-engine telemetry (System Monitor snippet, repurposed to REAL
 * data): API reachability, live queue depth, and a findings sparkline over
 * recent scans. `scans === null` means the API hasn't responded → offline.
 */
export function SystemMonitor({ scans }: { scans: ScanSummary[] | null }) {
  const [open, setOpen] = useState(false)

  const online = scans !== null
  const queue = scans?.filter((s) => s.status === "queued" || s.status === "running").length ?? 0
  const findings = (scans ?? [])
    .filter((s) => s.status === "completed" && s.created_at && s.analytics)
    .sort((a, b) => (a.created_at! < b.created_at! ? -1 : 1))
    .map((s) => s.analytics!.total_findings)
    .slice(-7)

  return (
    <div className="fixed bottom-4 right-4 z-40 hidden w-64 md:block">
      <div className="glass overflow-hidden rounded-md">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
          aria-expanded={open}
        >
          <span className="flex items-center gap-2">
            <Activity className={`h-4 w-4 ${online ? "text-scan" : "text-sev-certain"}`} aria-hidden />
            <span className="text-sm font-medium text-text">Scan Engine</span>
          </span>
          <span className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${online ? "bg-sev-clean animate-orbit-pulse" : "bg-sev-certain"}`}
              aria-hidden
            />
            <ChevronDown className={`h-4 w-4 text-text-faint transition-transform ${open ? "rotate-180" : ""}`} />
          </span>
        </button>

        {open && (
          <div className="space-y-3 border-t border-border px-4 py-3">
            <Row label="API" value={online ? "Online" : "Offline"} tone={online ? "good" : "bad"} />
            <Row label="Queue depth" value={String(queue)} tone={queue > 0 ? "warn" : "muted"} />
            <div>
              <div className="mb-1 text-xs text-text-faint">Recent findings</div>
              {findings.length >= 2 ? (
                <MiniSparkline data={findings} color="var(--brand-teal)" height={32} />
              ) : (
                <div className="text-xs text-text-faint">Not enough data yet</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value, tone }: { label: string; value: string; tone: "good" | "bad" | "warn" | "muted" }) {
  const color =
    tone === "good"
      ? "text-sev-clean"
      : tone === "bad"
        ? "text-sev-certain"
        : tone === "warn"
          ? "text-sev-medium"
          : "text-text"
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-text-muted">{label}</span>
      <span className={`tnum font-medium ${color}`}>{value}</span>
    </div>
  )
}
