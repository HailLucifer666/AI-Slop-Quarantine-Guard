import { ArrowDown, ArrowUp, type LucideIcon } from "lucide-react"
import { MiniSparkline } from "@/components/charts/MiniSparkline"
import type { Trend } from "@/lib/trend"

/**
 * KPI card with an optional delta arrow + trend sparkline (the Check-Box mockup
 * style). `goodWhen` decides delta tint: for findings/certain a rise is bad; for
 * clean-rate a rise is good. Delta is hidden (—) when trend has <2 points.
 */
export function KpiCardV2({
  icon: Icon,
  label,
  value,
  trend,
  goodWhen = "down",
  sparkColor = "var(--brand-teal)",
  tone,
}: {
  icon: LucideIcon
  label: string
  value: string
  trend?: Trend
  goodWhen?: "up" | "down"
  sparkColor?: string
  tone?: "alert" | "good"
}) {
  const valueColor =
    tone === "alert" ? "text-sev-certain" : tone === "good" ? "text-sev-clean" : "text-text"

  const delta = trend?.delta ?? null
  const rising = delta != null && delta > 0
  const falling = delta != null && delta < 0
  const isGood = delta == null ? false : goodWhen === "up" ? rising : falling
  const deltaColor = delta == null || delta === 0 ? "text-text-faint" : isGood ? "text-sev-clean" : "text-sev-certain"

  return (
    <div className="glass rounded-lg p-5 transition-transform hover:-translate-y-0.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-text-faint">
          <Icon className="h-4 w-4 text-brand-teal" aria-hidden />
          {label}
        </div>
        <span className={`tnum flex items-center gap-0.5 text-xs ${deltaColor}`}>
          {delta == null || delta === 0 ? (
            "—"
          ) : (
            <>
              {rising ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
              {Math.abs(delta)}
            </>
          )}
        </span>
      </div>
      <div className={`mt-3 tnum text-3xl font-bold ${valueColor}`}>{value}</div>
      {trend && trend.series.length >= 2 && (
        <div className="mt-2">
          <MiniSparkline data={trend.series} color={sparkColor} height={32} />
        </div>
      )}
    </div>
  )
}
