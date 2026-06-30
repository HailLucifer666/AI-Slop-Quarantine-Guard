import type { HeatCell } from "@/lib/useWallData"

/**
 * Reference's "Contribution Graph" — last 13 weeks of scans as week-columns of
 * dots, intensity = scan count (4 buckets), exact count in the tooltip, faint
 * column axis ticks + Less→More legend. Transparent / card-less.
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

export function ContribHeatmap({ cells }: { cells: HeatCell[] }) {
  const max = Math.max(1, ...cells.map((c) => c.count))
  const weeks = chunkWeeks(cells)
  const empty = cells.every((c) => c.count === 0)
  // ~5 evenly spaced axis ticks.
  const ticks = [1, 2, 3, 4, 5].map((n) => Math.round((n / 5) * weeks.length))

  return (
    <div className="relative flex flex-col">
      <div className="flex items-center justify-between">
        <span className="wall-label">Contribution Graph</span>
        <span className="flex items-center gap-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--wall-faint)" }}>
          Less
          {STEP_OPACITY.map((o, i) => (
            <span key={i} className="h-2 w-2 rounded-[2px]" style={{ background: o === 0 ? "var(--wall-line)" : "var(--wall-green)", opacity: o === 0 ? 1 : o }} aria-hidden />
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
                  className="h-2.5 w-2.5 rounded-[2px]"
                  style={{ background: b === 0 ? "var(--wall-line)" : "var(--wall-green)", opacity: b === 0 ? 1 : STEP_OPACITY[b] }}
                />
              )
            })}
          </div>
        ))}
      </div>

      <div className="mt-2 flex justify-between px-1 text-[10px]" style={{ color: "var(--wall-faint)" }}>
        {ticks.map((_, i) => (
          <span key={i} className="wall-num">
            {i + 1}
          </span>
        ))}
      </div>

      {empty && (
        <span className="pointer-events-none absolute inset-x-0 top-1/2 text-center text-xs" style={{ color: "var(--wall-faint)" }}>
          No scans recorded yet
        </span>
      )}
    </div>
  )
}
