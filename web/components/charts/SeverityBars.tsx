"use client"

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis } from "recharts"
import { RULE_IDS, checkName } from "@/lib/checks"

const RULE_COLOR: Record<string, string> = {
  SQG001: "#FF3B5C", // fake pkg (block-eligible)
  SQG002: "#FF3B5C", // secret (block-eligible)
  SQG003: "#FFC83D", // placeholder
  SQG004: "#FF8A3D", // CVE
  SQG005: "#FF8A3D", // license
  SQG006: "#FF8A3D", // SAST
  SQG007: "#FFC83D", // typosquat (advisory)
  SQG009: "#FFC83D", // avoidable complexity (advisory)
}
const RULES = RULE_IDS

export function SeverityBars({ byRule }: { byRule: Record<string, number> }) {
  const data = RULES.map((id) => ({ id, name: id, value: byRule[id] ?? 0 }))
  const hasData = data.some((d) => d.value > 0)

  return (
    <div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <XAxis dataKey="name" tick={{ fill: "#5B6472", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(120,140,255,0.06)" }}
            contentStyle={{ background: "#141922", border: "1px solid rgba(120,140,255,0.22)", borderRadius: 10, color: "#EAEEF6" }}
            formatter={(v: number, _n, p) => [`${v} finding(s)`, checkName((p.payload as { id: string }).id)]}
          />
          <Bar dataKey="value" radius={[6, 6, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.id} fill={RULE_COLOR[d.id]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {/* Text fallback for screen readers / no-data */}
      <p className="sr-only">
        {hasData
          ? data.filter((d) => d.value).map((d) => `${checkName(d.id)}: ${d.value}`).join(", ")
          : "No findings recorded yet."}
      </p>
      {!hasData && <p className="mt-2 text-center text-xs text-text-faint">No findings yet</p>}
    </div>
  )
}
