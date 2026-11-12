"use client"

import { MiniSparkline } from "@/components/charts/MiniSparkline"
import type { ScanSummary } from "@/lib/types"

/**
 * Bottom-strip tiles 2 + 4 (spec §5): the findings trend (honest, kept, with an
 * sr-only summary) and engine telemetry (the honest panel — logic untouched;
 * only the 12px type floor and token names applied).
 */

/**
 * Compact findings-over-time trend for the dashboard bottom strip. Real data:
 * total findings (certain+high+medium) per completed scan, chronologically.
 */
export function FindingsTrend({ series }: { series: { certain: number; high: number; medium: number }[] }) {
  const totals = series.map((s) => s.certain + s.high + s.medium)
  const last = totals[totals.length - 1] ?? 0
  const peak = totals.length ? Math.max(...totals) : 0

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <span className="wall-label">Findings Trend</span>
        <span className="text-xs" style={{ color: "var(--text-faint)" }}>{totals.length} scans</span>
      </div>
      <p className="sr-only">
        Latest {last}, peak {peak} findings over {totals.length} completed scans.
      </p>
      {totals.length >= 2 ? (
        <>
          <div className="mt-2 flex-1">
            <MiniSparkline data={totals} color="var(--accent-violet)" height={56} />
          </div>
          <div className="mt-1 flex items-center justify-between text-xs">
            <span style={{ color: "var(--text-muted)" }}>latest <span className="wall-num" style={{ color: "var(--text)" }}>{last}</span></span>
            <span style={{ color: "var(--text-muted)" }}>peak <span className="wall-num" style={{ color: "var(--text)" }}>{peak}</span></span>
          </div>
        </>
      ) : (
        <p className="wall-sub mt-3">Trend appears after 2+ completed scans.</p>
      )}
    </div>
  )
}

/**
 * Honest engine telemetry — reachability, queue depth, recent throughput, and
 * average scan duration, all derived from real scan records. No fabricated
 * CPU/RAM gauges (the backend exposes none); every reading traces to data.
 */
export function EngineTelemetry({ scans, online, scannedRecent }: { scans: ScanSummary[]; online: boolean; scannedRecent: number }) {
  const queue = scans.filter((s) => s.status === "queued" || s.status === "running").length
  const completed = scans.filter((s) => s.status === "completed")
  const durs = completed.map((s) => s.duration_ms).filter((d): d is number => typeof d === "number")
  const avgSec = durs.length ? durs.reduce((a, b) => a + b, 0) / durs.length / 1000 : null

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <span className="wall-label">Engine</span>
        <span className="flex items-center gap-1.5 text-xs" style={{ color: online ? "var(--accent-green)" : "var(--act-failed)" }}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: online ? "var(--accent-green)" : "var(--act-failed)" }} aria-hidden />
          {online ? "Online" : "Offline"}
        </span>
      </div>
      <div className="mt-2 grid flex-1 grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <Reading label="Queue depth" value={String(queue)} warn={queue > 0} />
        <Reading label="Last 10 min" value={String(scannedRecent)} />
        <Reading label="Avg scan" value={avgSec != null ? `${avgSec.toFixed(1)}s` : "—"} />
        <Reading label="Completed" value={String(completed.length)} />
      </div>
    </div>
  )
}

function Reading({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex flex-col">
      <span style={{ color: "var(--text-faint)" }}>{label}</span>
      <span className="wall-num text-sm" style={{ color: warn ? "var(--sev-medium)" : "var(--text)" }}>{value}</span>
    </div>
  )
}
