"use client"

import "@/app/dashboard/wall.css"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"

import { AuthGate } from "@/components/auth/AuthGate"
import { CommandDock } from "@/components/wall/panels/CommandDock"
import { CommandPalette } from "@/components/wall/panels/CommandPalette"
import type { Panel } from "@/components/wall/usePanel"
import { cn } from "@/lib/utils"

/**
 * App chrome. The cockpit IS the app — there is no sidebar. /login renders bare
 * (brings its own backdrop); every other route is gated and full-bleed.
 *
 * The Command Wall shell — the `.wall-root` wrapper, the top `CommandDock` nav,
 * and the ⌘K palette — lives HERE so it stays mounted across navigations. Pages
 * render only their panel, so a tab click swaps content without tearing down and
 * rebuilding the whole shell (the old per-page dock caused the stuttery, dead-
 * feeling navigation). The dashboard alone pins to the viewport height.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [paletteOpen, setPaletteOpen] = useState(false)

  // ⌘K / Ctrl-K opens the palette from anywhere in the shell.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener("keydown", on)
    return () => window.removeEventListener("keydown", on)
  }, [])

  // "/" renders the boot splash bare (own full-bleed backdrop); /login likewise.
  if (pathname?.startsWith("/login") || pathname === "/") return <>{children}</>

  const isDashboard = pathname === "/dashboard"

  return (
    <AuthGate>
      <div className={cn("wall-root flex min-h-dvh flex-col", isDashboard && "lg:h-dvh lg:overflow-hidden")}>
        <CommandDock onPalette={() => setPaletteOpen(true)} />
        {children}
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onJump={(p: Panel) => {
            setPaletteOpen(false)
            router.push(`/${p}`)
          }}
          onScanUrl={(u) => {
            setPaletteOpen(false)
            router.push(`/scan?url=${encodeURIComponent(u)}`)
          }}
        />
      </div>
    </AuthGate>
  )
}
