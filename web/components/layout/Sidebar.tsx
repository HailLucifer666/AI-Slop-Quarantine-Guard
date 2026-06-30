"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { LayoutDashboard, ListChecks, Menu, Radar, ScanLine, Settings, ShieldCheck, X } from "lucide-react"

import { cn } from "@/lib/utils"

/** Nav rail items. Routes land in Stage 4–5; the rail + active state ship now. */
const NAV = [
  { href: "/scan", label: "Scan", icon: ScanLine },
  { href: "/dashboard", label: "Command", icon: LayoutDashboard },
  { href: "/analyses", label: "Analyses", icon: ListChecks },
  { href: "/checks", label: "Checks", icon: Radar },
  { href: "/settings", label: "Settings", icon: Settings },
]

function Wordmark({ onClick }: { onClick?: () => void }) {
  return (
    <Link href="/" onClick={onClick} className="flex items-center gap-3 px-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-md bg-brand-gradient shadow-glow">
        <ShieldCheck className="h-5 w-5 text-bg" aria-hidden />
      </span>
      <span className="font-display text-sm font-bold uppercase leading-tight tracking-wide text-text">
        Slop
        <br />
        Quarantine Guard
      </span>
    </Link>
  )
}

export function Sidebar() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setOpen(false), [pathname])

  return (
    <>
      {/* Mobile top bar (< md): compact wordmark + hamburger. */}
      <header className="glass fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-x-0 border-t-0 px-4 md:hidden">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-gradient shadow-glow">
            <ShieldCheck className="h-4 w-4 text-bg" aria-hidden />
          </span>
          <span className="font-display text-xs font-bold uppercase tracking-wide text-text">
            Quarantine Guard
          </span>
        </Link>
        <button
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          className="flex h-11 w-11 items-center justify-center rounded-md text-text-muted hover:bg-surface hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo"
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>
      </header>

      {/* Backdrop behind the drawer on mobile. */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          aria-hidden
        />
      )}

      {/* The rail — a slide-in drawer on mobile, a fixed rail from md up. */}
      <aside
        className={cn(
          "glass fixed inset-y-0 left-0 z-40 flex w-[240px] flex-col gap-2 rounded-none border-y-0 border-l-0 px-4 py-6 transition-transform",
          open ? "translate-x-0" : "-translate-x-full",
          "md:z-20 md:translate-x-0",
        )}
      >
        <div className="mb-6 flex items-center justify-between">
          <Wordmark onClick={() => setOpen(false)} />
          <button
            onClick={() => setOpen(false)}
            aria-label="Close menu"
            className="flex h-9 w-9 items-center justify-center rounded-md text-text-muted hover:bg-surface hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo md:hidden"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        <nav className="flex flex-col gap-1" aria-label="Primary">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/")
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                  "min-h-[44px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo",
                  active
                    ? "bg-surface-elevated text-text shadow-glass"
                    : "text-text-muted hover:bg-surface hover:text-text",
                )}
              >
                <Icon
                  className={cn("h-5 w-5 shrink-0", active ? "text-brand-teal" : "text-text-faint group-hover:text-text-muted")}
                  aria-hidden
                />
                {label}
              </Link>
            )
          })}
        </nav>

        <div className="mt-auto px-3 text-xs text-text-faint">
          <span className="tnum">v0.1</span> · Aurora foundation
        </div>
      </aside>
    </>
  )
}
