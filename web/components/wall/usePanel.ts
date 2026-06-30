"use client"

import { useCallback, useEffect, useState } from "react"

/**
 * Overlay state for the cockpit, synced to the URL (`?panel=…&id=…`) via the
 * History API — no next/navigation searchParams (avoids the Suspense build
 * requirement on a static client page). Reads on mount (deep links from the
 * retired routes) and on back/forward (popstate).
 */
export type Panel = "scan" | "analyses" | "analysis" | "checks" | "settings"

function read(): { panel: Panel | null; id: string | null } {
  if (typeof window === "undefined") return { panel: null, id: null }
  const p = new URLSearchParams(window.location.search)
  return { panel: (p.get("panel") as Panel | null) || null, id: p.get("id") }
}

export function usePanel() {
  const [state, setState] = useState<{ panel: Panel | null; id: string | null }>({ panel: null, id: null })

  useEffect(() => {
    setState(read())
    const on = () => setState(read())
    window.addEventListener("popstate", on)
    return () => window.removeEventListener("popstate", on)
  }, [])

  const open = useCallback((panel: Panel, id?: string | number) => {
    const p = new URLSearchParams(window.location.search)
    p.set("panel", panel)
    if (id != null) p.set("id", String(id))
    else p.delete("id")
    window.history.pushState(null, "", `${window.location.pathname}?${p.toString()}`)
    setState({ panel, id: id != null ? String(id) : null })
  }, [])

  const close = useCallback(() => {
    const p = new URLSearchParams(window.location.search)
    p.delete("panel")
    p.delete("id")
    const q = p.toString()
    window.history.pushState(null, "", q ? `${window.location.pathname}?${q}` : window.location.pathname)
    setState({ panel: null, id: null })
  }, [])

  return { ...state, open, close }
}
