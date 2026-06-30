"use client"

import { useEffect, useRef, useState } from "react"

import { formatNumber } from "@/lib/format"
import { useReducedMotion } from "./useReducedMotion"

const easeOut = (p: number) => 1 - Math.pow(1 - p, 3)

/** Center "events" mode — a large count-up number. Reduced-motion shows it instantly. */
export function EventsCounter({ value, label, sublabel }: { value: number; label: string; sublabel?: string }) {
  const [display, setDisplay] = useState(0)
  const reduced = useReducedMotion()
  const fromRef = useRef(0)

  useEffect(() => {
    if (reduced) {
      setDisplay(value)
      return
    }
    const from = fromRef.current
    let raf = 0
    let startT = 0
    const dur = 1100
    const tick = (t: number) => {
      if (!startT) startT = t
      const p = Math.min(1, (t - startT) / dur)
      setDisplay(Math.round(from + (value - from) * easeOut(p)))
      if (p < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, reduced])

  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <div className="wall-label">{label}</div>
      <div
        className="wall-num wall-glow-cyan mt-2 text-[clamp(3rem,9vw,7rem)]"
        style={{ color: "var(--wall-cyan)" }}
      >
        {formatNumber(display)}
      </div>
      {sublabel && (
        <div className="mt-2 text-xs uppercase tracking-wide" style={{ color: "var(--wall-faint)" }}>
          {sublabel}
        </div>
      )}
    </div>
  )
}
