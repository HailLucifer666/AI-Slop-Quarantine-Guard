"use client"

import { MiniSparkline } from "@/components/charts/MiniSparkline"
import type { ScanSummary } from "@/lib/types"

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
        <span className="text-[10px] uppercase tracking-wide" style={{ color: "var(--wall-faint)" }}>{totals.length} scans</span>
      </div>
      {totals.length >= 2 ? (
        <>
          <div className="mt-2 flex-1">
            <MiniSparkline data={totals} color="var(--wall-violet)" height={56} />
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px]">
            <span style={{ color: "var(--wall-muted)" }}>latest <span className="wall-num" style={{ color: "var(--wall-text)" }}>{last}</span></span>
            <span style={{ color: "var(--wall-muted)" }}>peak <span className="wall-num" style={{ color: "var(--wall-text)" }}>{peak}</span></span>
          </div>
        </>
      ) : (
        <p className="mt-3 text-xs" style={{ color: "var(--wall-faint)" }}>Trend appears after 2+ completed scans.</p>
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
        <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide" style={{ color: online ? "var(--wall-green)" : "var(--wall-act-failed)" }}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: online ? "var(--wall-green)" : "var(--wall-act-failed)" }} aria-hidden />
          {online ? "Online" : "Offline"}
        </span>
      </div>
      <div className="mt-2 grid flex-1 grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
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
      <span style={{ color: "var(--wall-faint)" }}>{label}</span>
      <span className="wall-num text-sm" style={{ color: warn ? "var(--wall-sev-medium)" : "var(--wall-text)" }}>{value}</span>
    </div>
  )
}
