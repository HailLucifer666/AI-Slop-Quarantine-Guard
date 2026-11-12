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
      <div className="flex items-center justify-between gap-3 px-4 py-0.5 md:px-6">
        <Link href="/dashboard" className="wall-focus flex items-center gap-2.5 py-1" aria-label="Command wall">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-md"
            style={{ background: "var(--brand-gradient)" }}
          >
            <ShieldCheck className="h-4 w-4" style={{ color: "var(--on-accent)" }} aria-hidden />
          </span>
          <span
            className="hidden font-display text-sm font-bold uppercase tracking-wide sm:inline"
            style={{ color: "var(--text)" }}
          >
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
                className="wall-focus flex min-h-[44px] items-center gap-1.5 rounded-md border px-3 text-sm transition-colors md:gap-2"
                style={{
                  color: on ? "var(--text)" : "var(--text-muted)",
                  background: on ? "rgba(255,255,255,0.06)" : "transparent",
                  borderColor: on ? "var(--line-strong)" : "transparent",
                }}
              >
                <t.icon className="h-4 w-4" aria-hidden />
                <span>{t.label}</span>
              </Link>
            )
          })}
        </nav>

        <div className="flex items-center gap-3 text-xs" style={{ color: "var(--text-faint)" }}>
          {onPalette && (
            <button
              onClick={onPalette}
              className="wall-focus relative hidden items-center rounded-md px-2 py-1 sm:flex"
              style={{ border: "1px solid var(--line)" }}
              aria-label="Command palette"
            >
              {/* Pseudo-element extends the 28px visual to a 44px hit target. */}
              <span className="absolute -inset-2" aria-hidden />
              <span className="wall-num font-mono text-xs">⌘K</span>
            </button>
          )}
          <span className="flex items-center gap-1.5">
            <span
              className={live ? "h-1.5 w-1.5 animate-pulse rounded-full" : "h-1.5 w-1.5 rounded-full"}
              style={{ background: live ? "var(--accent-green)" : "var(--text-faint)" }}
              aria-hidden
            />
            {live ? "Live" : "Offline"}
          </span>
        </div>
      </div>
    </header>
  )
}
