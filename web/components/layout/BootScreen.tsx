"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import { motion, useReducedMotion } from "framer-motion"
import { ShieldCheck } from "lucide-react"

// The dot-matrix is a client-only WebGL canvas — load it without SSR.
const FallingDotMatrix = dynamic(() => import("@/components/effects/FallingDotMatrix"), { ssr: false })

const BOOT_LINES = [
  "loading analyzers · SQG001–006",
  "linking deterministic Guard core",
  "connecting scan engine · :8000",
  "rendering Command Wall",
]

/**
 * Initializing boot splash shown at "/" — the FallingDotMatrix field behind a
 * brand mark, a real progress bar, and sequenced boot lines, then it hands off
 * to the dashboard. No password step; the splash IS the entry. Reduced-motion →
 * no matrix, near-instant handoff.
 */
export function BootScreen() {
  const router = useRouter()
  const reduce = useReducedMotion()
  const duration = reduce ? 0.4 : 2.2
  const [step, setStep] = useState(0)

  useEffect(() => {
    const go = setTimeout(() => router.replace("/dashboard"), duration * 1000)
    return () => clearTimeout(go)
  }, [router, duration])

  useEffect(() => {
    if (reduce) {
      setStep(BOOT_LINES.length)
      return
    }
    const per = (duration * 1000) / (BOOT_LINES.length + 1)
    const timers = BOOT_LINES.map((_, i) => setTimeout(() => setStep(i + 1), per * (i + 1)))
    return () => timers.forEach(clearTimeout)
  }, [reduce, duration])

  return (
    <div className="wall-root fixed inset-0 z-[60] flex items-center justify-center overflow-hidden">
      <div
        className="absolute inset-0 -z-10"
        style={{ background: "radial-gradient(125% 95% at 50% 30%, #05070f 0%, #02030a 55%, #000000 100%)" }}
      />
      <FallingDotMatrix />

      <div className="relative z-10 flex w-[min(90vw,440px)] flex-col items-center px-6 text-center">
        <motion.div
          initial={reduce ? false : { scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="flex h-14 w-14 items-center justify-center rounded-2xl"
          style={{ border: "1px solid var(--wall-line-strong)", background: "var(--wall-panel)" }}
        >
          <ShieldCheck className="h-7 w-7" style={{ color: "var(--wall-cyan)" }} aria-hidden />
        </motion.div>

        <div className="wall-grad-cool mt-4 text-lg font-semibold tracking-[0.2em]">AI SLOP QUARANTINE GUARD</div>
        <div className="wall-label mt-1" style={{ color: "var(--wall-muted)" }}>Initializing</div>

        <div className="mt-5 h-1 w-full overflow-hidden rounded-full" style={{ background: "var(--wall-line)" }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: "linear-gradient(90deg, var(--wall-violet), var(--wall-cyan))" }}
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ duration, ease: "easeInOut" }}
          />
        </div>

        <ul className="mt-5 w-full space-y-1.5 text-left">
          {BOOT_LINES.map((line, i) => (
            <li
              key={line}
              className="wall-mono flex items-center gap-2 text-[11px] transition-opacity duration-300"
              style={{ opacity: i < step ? 1 : 0.25, color: i < step ? "var(--wall-text)" : "var(--wall-faint)" }}
            >
              <span style={{ color: i < step ? "var(--wall-green)" : "var(--wall-faint)" }}>{i < step ? "✓" : "▸"}</span>
              {line}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
