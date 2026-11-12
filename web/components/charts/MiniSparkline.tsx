"use client"

import { useId } from "react"
import { Area, AreaChart, ResponsiveContainer } from "recharts"

/**
 * Tiny axis-less area sparkline for KPI cards / top-check cards / system monitor.
 * Needs >=2 points to draw; renders a spacer otherwise (sparse-data safe).
 */
export function MiniSparkline({
  data,
  color = "var(--accent-cyan)",
  height = 36,
}: {
  data: number[]
  color?: string
  height?: number
}) {
  const gid = useId().replace(/:/g, "")
  if (!data || data.length < 2) return <div style={{ height }} aria-hidden />

  const chartData = data.map((v, i) => ({ i, v }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`spark-${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#spark-${gid})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
