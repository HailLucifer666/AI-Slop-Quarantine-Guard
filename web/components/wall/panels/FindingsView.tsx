"use client"

import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"

import { getScan } from "@/lib/api"
import { isTerminal, type ScanDetail } from "@/lib/types"
import { ScanResults } from "./ScanResults"

const POLL_MS = 2000

/** Per-scan report page (/analyses/[id]). Polls until terminal, then renders the
 * shared ScanResults view (stats, radial charts, per-check strip, findings). */
export function FindingsView({ id }: { id: string }) {
  const [scan, setScan] = useState<ScanDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function tick() {
      try {
        const data = await getScan(id)
        if (!active) return
        setScan(data)
        if (!isTerminal(data.status)) timer = setTimeout(tick, POLL_MS)
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Failed to load scan.")
      }
    }
    tick()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [id])

  if (error) return <p className="text-sm" style={{ color: "var(--act-failed)" }}>{error}</p>
  if (!scan) return <p className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}><Loader2 className="h-4 w-4 animate-spin" /> Loading scan…</p>

  return <ScanResults scan={scan} />
}
