"use client"

import { useEffect, useRef, useState } from "react"

import { useReducedMotion } from "./useReducedMotion"

/** RAF count-up — 600ms ease-out on the cockpit hero and tile lead figures, on
 * mount and on every value change (spec §10.5). Renders the raw value instantly
 * under reduced motion or when disabled. Tabular figures keep width stable. */
export function useCountUp(value: number, opts: { duration?: number; disabled?: boolean } = {}): number {
  const { duration = 600, disabled = false } = opts
  const reduced = useReducedMotion()
  const [display, setDisplay] = useState(value)
  const displayRef = useRef(value)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (reduced || disabled) {
      displayRef.current = value
      setDisplay(value)
      return
    }
    const from = displayRef.current
    if (from === value) return
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3) // ease-out cubic
      const v = Math.round(from + (value - from) * eased)
      displayRef.current = v
      setDisplay(v)
      if (t < 1) rafRef.current = requestAnimationFrame(step)
    }
    rafRef.current = requestAnimationFrame(step)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [value, reduced, disabled, duration])

  return display
}

/** Returns true only when `active` has held for `ms` (default 300) — gates every
 * skeleton render so fast loads never flash placeholders (spec §10.6, §7). */
export function useDelayedFlag(active: boolean, ms = 300): boolean {
  const [flag, setFlag] = useState(false)

  useEffect(() => {
    if (!active) {
      setFlag(false)
      return
    }
    const t = setTimeout(() => setFlag(true), ms)
    return () => clearTimeout(t)
  }, [active, ms])

  return flag
}
