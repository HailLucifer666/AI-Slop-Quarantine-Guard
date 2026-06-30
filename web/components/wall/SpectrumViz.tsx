"use client"

/**
 * Center "spectrum" mode — per-completed-scan severity rendered as a mirrored
 * waveform. Each column's height = weighted finding load; color = worst severity
 * present. Legend + aria summary make it readable without relying on color alone.
 */
type Series = { certain: number; high: number; medium: number }

function weight(s: Series): number {
  return s.certain * 3 + s.high * 2 + s.medium
}

function colorOf(s: Series): string {
  if (s.certain > 0) return "var(--wall-sev-certain)"
  if (s.high > 0) return "var(--wall-sev-high)"
  if (s.medium > 0) return "var(--wall-sev-medium)"
  return "var(--wall-sev-clean)"
}

const LEGEND: { label: string; color: string }[] = [
  { label: "Certain", color: "var(--wall-sev-certain)" },
  { label: "High", color: "var(--wall-sev-high)" },
  { label: "Medium", color: "var(--wall-sev-medium)" },
  { label: "Clean", color: "var(--wall-sev-clean)" },
]

export function SpectrumViz({ series }: { series: Series[] }) {
  const max = Math.max(1, ...series.map(weight))
  const totals = series.reduce(
    (acc, s) => ({ certain: acc.certain + s.certain, high: acc.high + s.high, medium: acc.medium + s.medium }),
    { certain: 0, high: 0, medium: 0 },
  )

  return (
    <figure className="flex h-full flex-col">
      <figcaption className="sr-only">
        Severity spectrum across {series.length} completed scans: {totals.certain} certain, {totals.high} high,
        {" "}
        {totals.medium} medium findings.
      </figcaption>

      <div className="wall-label text-center">Severity Spectrum</div>

      <div className="flex flex-1 items-center justify-center gap-[3px] px-2 py-4">
        {series.length === 0 ? (
          <span className="text-xs" style={{ color: "var(--wall-faint)" }}>
            No completed scans yet
          </span>
        ) : (
          series.slice(-60).map((s, i) => {
            const h = Math.max(2, (weight(s) / max) * 100)
            const color = colorOf(s)
            return (
              <div key={i} className="flex h-full flex-1 items-center" style={{ maxWidth: 14 }}>
                <span
                  className="mx-auto w-full rounded-full"
                  style={{
                    height: `${h}%`,
                    minHeight: 3,
                    background: color,
                    boxShadow: weight(s) > 0 ? `0 0 8px ${color}` : "none",
                    opacity: weight(s) > 0 ? 0.95 : 0.4,
                  }}
                />
              </div>
            )
          })
        )}
      </div>

      <div className="flex items-center justify-center gap-4 pb-1">
        {LEGEND.map((l) => (
          <span key={l.label} className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide" style={{ color: "var(--wall-muted)" }}>
            <span className="h-2 w-2 rounded-full" style={{ background: l.color }} aria-hidden />
            {l.label}
          </span>
        ))}
      </div>
    </figure>
  )
}
