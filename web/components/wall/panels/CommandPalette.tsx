"use client"

import { useEffect, useRef, useState } from "react"
import { ListChecks, Radar, ScanLine, Settings } from "lucide-react"

import type { Panel } from "@/components/wall/usePanel"

/** ⌘K palette — type a repo URL to scan, or jump to any surface. */
const JUMPS: { id: Panel; label: string; icon: typeof ScanLine }[] = [
  { id: "scan", label: "New scan", icon: ScanLine },
  { id: "analyses", label: "Analyses", icon: ListChecks },
  { id: "checks", label: "Checks", icon: Radar },
  { id: "settings", label: "Settings", icon: Settings },
]
const looksUrl = (s: string) => /^(https?:\/\/|git@|github\.com|gitlab\.com)/i.test(s.trim())

export function CommandPalette({
  open,
  onClose,
  onJump,
  onScanUrl,
}: {
  open: boolean
  onClose: () => void
  onJump: (p: Panel) => void
  onScanUrl: (url: string) => void
}) {
  const [q, setQ] = useState("")
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) setQ("")
  }, [open])

  // Trap Tab inside the dialog so focus can't escape to the page behind it.
  function onKeyDownTrap(e: React.KeyboardEvent) {
    if (e.key !== "Tab" || !panelRef.current) return
    const items = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>('input, button, textarea, [href], [tabindex]:not([tabindex="-1"])'),
    ).filter((el) => el.offsetParent !== null)
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement
    if (e.shiftKey && active === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", on)
    return () => window.removeEventListener("keydown", on)
  }, [onClose])

  if (!open) return null

  const submit = () => {
    if (looksUrl(q)) onScanUrl(q.trim())
    else onJump("scan")
  }

  return (
    <div ref={panelRef} onKeyDown={onKeyDownTrap} className="fixed inset-0 z-[60] flex items-start justify-center pt-[14vh]" role="dialog" aria-modal="true" aria-label="Command palette">
      <button aria-label="Close" onClick={onClose} className="absolute inset-0 cursor-default" style={{ background: "rgba(2,4,10,0.6)", backdropFilter: "blur(6px)" }} />
      <div className="relative z-10 w-[min(560px,92vw)] overflow-hidden rounded-2xl" style={{ background: "var(--wall-panel-solid)", border: "1px solid var(--wall-line-strong)", boxShadow: "0 30px 100px -20px rgba(0,0,0,0.8)" }}>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Type a repo URL to scan, or pick below…"
          className="w-full bg-transparent px-5 py-4 text-sm outline-none"
          style={{ color: "var(--wall-text)", borderBottom: "1px solid var(--wall-line)" }}
        />
        <ul className="p-2">
          {looksUrl(q) && (
            <li>
              <button onClick={submit} className="wall-focus flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-white/5" style={{ color: "var(--wall-text)" }}>
                <ScanLine className="h-4 w-4" style={{ color: "var(--wall-cyan)" }} aria-hidden /> Scan <span className="font-mono" style={{ color: "var(--wall-muted)" }}>{q.trim()}</span>
              </button>
            </li>
          )}
          {JUMPS.map((j) => (
            <li key={j.id}>
              <button onClick={() => onJump(j.id)} className="wall-focus flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-white/5" style={{ color: "var(--wall-text)" }}>
                <j.icon className="h-4 w-4" style={{ color: "var(--wall-muted)" }} aria-hidden /> {j.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
