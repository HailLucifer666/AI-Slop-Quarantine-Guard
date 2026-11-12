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
  const [active, setActive] = useState(0)
  const panelRef = useRef<HTMLDivElement>(null)

  // Row list: the URL row appears only when the query looks like a repo URL.
  const showScanRow = looksUrl(q)
  const rowCount = (showScanRow ? 1 : 0) + JUMPS.length

  useEffect(() => {
    if (open) {
      setQ("")
      setActive(0)
    }
  }, [open])

  // Keep the highlighted row in bounds when the URL row appears/disappears.
  useEffect(() => {
    setActive((i) => Math.min(i, rowCount - 1))
  }, [rowCount])

  // Trap Tab inside the dialog so focus can't escape to the page behind it.
  function onKeyDownTrap(e: React.KeyboardEvent) {
    if (e.key !== "Tab" || !panelRef.current) return
    const items = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>('input, button, textarea, [href], [tabindex]:not([tabindex="-1"])'),
    ).filter((el) => el.offsetParent !== null)
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    const activeEl = document.activeElement
    if (e.shiftKey && activeEl === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && activeEl === last) {
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

  const runRow = (i: number) => {
    if (showScanRow && i === 0) onScanUrl(q.trim())
    else onJump(JUMPS[i - (showScanRow ? 1 : 0)].id)
  }

  const onInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActive((i) => (rowCount === 0 ? 0 : (i + 1) % rowCount))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActive((i) => (rowCount === 0 ? 0 : (i - 1 + rowCount) % rowCount))
    } else if (e.key === "Enter") {
      e.preventDefault()
      runRow(active)
    }
  }

  return (
    <div
      ref={panelRef}
      onKeyDown={onKeyDownTrap}
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[14vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <button aria-label="Close" onClick={onClose} className="absolute inset-0 cursor-default" style={{ background: "rgba(2,4,10,0.6)", backdropFilter: "blur(6px)" }} />
      <div className="wall-card relative z-10 w-[min(560px,92vw)] overflow-hidden rounded-xl" style={{ boxShadow: "var(--elev-2)" }}>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onInputKeyDown}
          role="combobox"
          aria-expanded
          aria-controls="palette-options"
          aria-activedescendant={rowCount > 0 ? `palette-opt-${active}` : undefined}
          placeholder="Type a repo URL to scan, or pick below…"
          className="w-full bg-transparent px-5 py-3 text-md outline-none"
          style={{ color: "var(--text)", borderBottom: "1px solid var(--line)", minHeight: 48 }}
        />
        <ul id="palette-options" role="listbox" aria-label="Commands" className="p-2">
          {showScanRow && (
            <li role="option" id="palette-opt-0" aria-selected={active === 0}>
              <button
                onClick={() => runRow(0)}
                onMouseEnter={() => setActive(0)}
                className="wall-focus flex min-h-[44px] w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-base hover:bg-white/5"
                style={{ color: "var(--text)", background: active === 0 ? "rgba(255,255,255,0.05)" : undefined }}
              >
                <ScanLine className="h-4 w-4" style={{ color: "var(--accent-cyan)" }} aria-hidden /> Scan{" "}
                <span className="font-mono" style={{ color: "var(--text-muted)" }}>{q.trim()}</span>
              </button>
            </li>
          )}
          {JUMPS.map((j, i) => {
            const idx = i + (showScanRow ? 1 : 0)
            return (
              <li key={j.id} role="option" id={`palette-opt-${idx}`} aria-selected={active === idx}>
                <button
                  onClick={() => runRow(idx)}
                  onMouseEnter={() => setActive(idx)}
                  className="wall-focus flex min-h-[44px] w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-base hover:bg-white/5"
                  style={{ color: "var(--text)", background: active === idx ? "rgba(255,255,255,0.05)" : undefined }}
                >
                  <j.icon className="h-4 w-4" style={{ color: "var(--text-muted)" }} aria-hidden /> {j.label}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
