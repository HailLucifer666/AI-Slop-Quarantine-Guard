"use client"

import type { HeatCell } from "@/lib/useWallData"

/**
 * Bottom-strip tile 3 (spec §5) — 13 weeks of scans as week-columns of dots,
 * intensity = scan count (4 buckets), exact count in the tooltip, REAL date
 * axis labels (first/middle/last cell), a permanent "{n} scans so far" caption
 * (the 11-scan reality reads "small but alive", not broken), and an sr-only
 * summary so the ramp is never the only data channel.
 */
function chunkWeeks(cells: HeatCell[]): HeatCell[][] {
  const weeks: HeatCell[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}
function bucket(count: number, max: number): number {
  if (count === 0) return 0
  if (max <= 1) return 3
  const r = count / max
  if (r > 0.66) return 3
  if (r > 0.33) return 2
  return 1
}
const STEP_OPACITY = [0, 0.4, 0.7, 1]

/** ISO day (yyyy-mm-dd) → "Aug 18". T00:00:00 pins the parse to local midnight
 * (a bare date string parses as UTC and can shift a day west of GMT). */
function dayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })
}

export function ContribHeatmap({ cells, scanned }: { cells: HeatCell[]; scanned: number }) {
  const max = Math.max(1, ...cells.map((c) => c.count))
  const weeks = chunkWeeks(cells)
  const empty = cells.every((c) => c.count === 0)
  const total = cells.reduce((a, c) => a + c.count, 0)
  const busiest = cells.reduce<HeatCell | null>((acc, c) => (acc == null || c.count > acc.count ? c : acc), null)
  // Real axis: first, middle, and last cell of the 13-week window.
  const axis = [cells[0], cells[Math.floor((cells.length - 1) / 2)], cells[cells.length - 1]]

  return (
    <div className="relative flex flex-col">
      <div className="flex items-center justify-between">
        <span className="wall-label">Contribution Graph</span>
        <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text-faint)" }}>
          Less
          {STEP_OPACITY.map((o, i) => (
            <span
              key={i}
              className="h-2 w-2 rounded-xs"
              style={{ background: o === 0 ? "var(--line)" : "var(--accent-green)", opacity: o === 0 ? 1 : o }}
              aria-hidden
            />
          ))}
          More
        </span>
      </div>

      <div className="mt-3 flex flex-1 items-center gap-[3px]">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-[3px]">
            {week.map((cell) => {
              const b = bucket(cell.count, max)
              return (
                <span
                  key={cell.day}
                  title={`${cell.day}: ${cell.count} scan${cell.count === 1 ? "" : "s"}`}
                  className="h-2.5 w-2.5 rounded-xs"
                  style={{ background: b === 0 ? "var(--line)" : "var(--accent-green)", opacity: b === 0 ? 1 : STEP_OPACITY[b] }}
                />
              )
            })}
          </div>
        ))}
      </div>

      <div className="mt-2 flex justify-between px-1 text-xs" style={{ color: "var(--text-faint)" }}>
        {axis.map((c, i) => (
          <span key={i} className="wall-num">
            {c ? dayLabel(c.day) : ""}
          </span>
        ))}
      </div>
      <p className="wall-sub mt-1">{scanned} scans so far</p>
      <p className="sr-only">
        {total > 0 && busiest
          ? `${total} scans across the last 13 weeks; busiest day ${dayLabel(busiest.day)} with ${busiest.count}.`
          : "No scans in the last 13 weeks."}
      </p>

      {empty && (
        <span className="wall-sub pointer-events-none absolute inset-x-0 top-1/2 text-center">
          No scans in the last 13 weeks yet
        </span>
      )}
    </div>
  )
}
