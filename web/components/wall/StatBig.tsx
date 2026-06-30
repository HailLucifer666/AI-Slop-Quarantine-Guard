import Link from "next/link"
import type { LucideIcon } from "lucide-react"

/**
 * Big-number stat (reference's huge thin numerals). Transparent, card-less.
 * Optional gradient accent + optional href (the wall's tiles are navigation).
 */
export function StatBig({
  label,
  value,
  sub,
  accent = "plain",
  href,
  onClick,
  icon: Icon,
  size = "md",
}: {
  label: string
  value: string
  sub?: string
  accent?: "plain" | "pink" | "cool" | "warm"
  href?: string
  onClick?: () => void
  icon?: LucideIcon
  size?: "md" | "xl"
}) {
  const grad = accent === "pink" ? "wall-grad-pink" : accent === "cool" ? "wall-grad-cool" : accent === "warm" ? "wall-grad-warm" : ""
  const sizeCls = size === "xl" ? "text-[clamp(3rem,6.5vw,5.5rem)]" : "text-[clamp(2.1rem,4vw,3.6rem)]"

  const inner = (
    <>
      <div className="wall-label flex items-center gap-2">
        {Icon && <Icon className="h-3.5 w-3.5" style={{ color: "var(--wall-muted)" }} aria-hidden />}
        {label}
      </div>
      <div className={`wall-figure mt-2 ${sizeCls} ${grad}`}>{value}</div>
      {sub && (
        <div className="mt-1.5 text-[11px]" style={{ color: "var(--wall-faint)" }}>
          {sub}
        </div>
      )}
    </>
  )

  if (onClick) {
    return (
      <button onClick={onClick} className="wall-click wall-focus block min-w-0 text-left">
        {inner}
      </button>
    )
  }
  if (href) {
    return (
      <Link href={href} className="wall-click wall-focus block min-w-0">
        {inner}
      </Link>
    )
  }
  return <div className="min-w-0">{inner}</div>
}
