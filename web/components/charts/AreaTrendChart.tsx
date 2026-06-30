"use client"

import { useId } from "react"
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import type { ScanSummary } from "@/lib/types"

/**
 * Findings-over-time (nixtio mockup style): filled gradient area = total
 * findings per scan, dashed overlay = CERTAIN. Real data only — needs >=2
 * completed, timestamped scans, else shows an empty state.
 */
export function AreaTrendChart({ scans }: { scans: ScanSummary[] }) {
  const gid = useId().replace(/:/g, "")

  const data = scans
    .filter((s) => s.status === "completed" && s.created_at && s.analytics)
    .sort((a, b) => (a.created_at! < b.created_at! ? -1 : 1))
    .map((s) => ({
      date: s.created_at!.slice(5, 10), // MM-DD
      total: s.analytics!.total_findings,
      certain: s.analytics!.by_confidence?.CERTAIN ?? 0,
    }))

  if (data.length < 2) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-text-faint">
        Findings trend appears once you have 2+ completed scans.
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -16 }}>
        <defs>
          <linearGradient id={`trend-${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand-indigo)" stopOpacity={0.45} />
            <stop offset="100%" stopColor="var(--brand-indigo)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,140,255,0.08)" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: "#5B6472", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#5B6472", fontSize: 11 }} axisLine={false} tickLine={false} width={32} allowDecimals={false} />
        <Tooltip
          cursor={{ stroke: "rgba(120,140,255,0.25)" }}
          contentStyle={{
            background: "#141922",
            border: "1px solid rgba(120,140,255,0.22)",
            borderRadius: 10,
            color: "#EAEEF6",
          }}
        />
        <Area
          type="monotone"
          dataKey="total"
          name="All findings"
          stroke="var(--brand-indigo)"
          strokeWidth={2}
          fill={`url(#trend-${gid})`}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="certain"
          name="CERTAIN"
          stroke="var(--sev-certain)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          fill="none"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
