"use client"

import { useEffect, useState } from "react"

/** Track `prefers-reduced-motion` reactively (used to gate spin / cycle / count-up). */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)")
    const on = () => setReduced(m.matches)
    on()
    m.addEventListener?.("change", on)
    return () => m.removeEventListener?.("change", on)
  }, [])

  return reduced
}
