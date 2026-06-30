"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { ListChecks, Radar, ScanLine, Settings, ShieldCheck } from "lucide-react"

/**
 * Top command bar — the app's always-visible navigation. Brand → cockpit; the
 * four tabs are real links to dedicated pages; live status + ⌘K (cockpit only).
 */
const TABS: { href: string; label: string; icon: typeof ScanLine }[] = [
  { href: "/scan", label: "Scan", icon: ScanLine },
  { href: "/analyses", label: "Analyses", icon: ListChecks },
  { href: "/checks", label: "Checks", icon: Radar },
  { href: "/settings", label: "Settings", icon: Settings },
]

export function CommandDock({ onPalette, live = true }: { onPalette?: () => void; live?: boolean }) {
  const pathname = usePathname() || "/"

  return (
    <header className="relative shrink-0">
      <div className="wall-hairline" />
      <div className="flex items-center justify-between gap-3 px-4 py-2 md:px-6">
        <Link href="/dashboard" className="wall-focus flex items-center gap-2.5" aria-label="Command wall">
          <span className="flex h-7 w-7 items-center justify-center rounded-md" style={{ background: "linear-gradient(135deg, var(--wall-magenta), var(--wall-violet) 50%, var(--wall-cyan))" }}>
            <ShieldCheck className="h-4 w-4" style={{ color: "#04060c" }} aria-hidden />
          </span>
          <span className="hidden font-display text-sm font-bold uppercase tracking-wide sm:inline" style={{ color: "var(--wall-text)" }}>
            Command Wall
          </span>
        </Link>

        <nav className="flex items-center gap-1" aria-label="Primary">
          {TABS.map((t) => {
            const on = pathname === t.href || (t.href === "/analyses" && pathname.startsWith("/analyses"))
            return (
              <Link
                key={t.href}
                href={t.href}
                aria-current={on ? "page" : undefined}
                className="wall-focus flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors md:gap-2 md:px-3 md:text-sm"
                style={{ color: on ? "var(--wall-text)" : "var(--wall-muted)", background: on ? "var(--wall-line)" : "transparent" }}
              >
                <t.icon className="h-4 w-4" aria-hidden />
                <span>{t.label}</span>
              </Link>
            )
          })}
        </nav>

        <div className="flex items-center gap-3 text-[11px]" style={{ color: "var(--wall-faint)" }}>
          {onPalette && (
            <button onClick={onPalette} className="wall-focus hidden items-center gap-1 rounded-md px-2 py-1 sm:flex" style={{ border: "1px solid var(--wall-line)" }} aria-label="Command palette">
              <span className="wall-num">⌘K</span>
            </button>
          )}
          <span className="flex items-center gap-1.5 uppercase tracking-wide">
            <span className={live ? "h-1.5 w-1.5 animate-pulse rounded-full" : "h-1.5 w-1.5 rounded-full"} style={{ background: live ? "var(--wall-green)" : "var(--wall-faint)" }} aria-hidden />
            {live ? "Live" : "Offline"}
          </span>
        </div>
      </div>
    </header>
  )
}
