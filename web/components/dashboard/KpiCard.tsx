import type { LucideIcon } from "lucide-react"

export function KpiCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: "alert" | "good"
}) {
  const valueColor = tone === "alert" ? "text-sev-certain" : tone === "good" ? "text-sev-clean" : "text-text"
  return (
    <div className="glass rounded-lg p-5 transition-transform hover:-translate-y-0.5">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-text-faint">
        <Icon className="h-4 w-4 text-brand-teal" aria-hidden />
        {label}
      </div>
      <div className={`mt-3 tnum text-3xl font-bold ${valueColor}`}>{value}</div>
    </div>
  )
}
