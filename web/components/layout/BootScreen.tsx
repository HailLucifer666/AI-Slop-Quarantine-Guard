"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import { motion, useReducedMotion } from "framer-motion"
import { Check, ChevronRight, ShieldCheck } from "lucide-react"

// The dot-matrix is a client-only WebGL canvas — load it without SSR.
const FallingDotMatrix = dynamic(() => import("@/components/effects/FallingDotMatrix"), { ssr: false })

const BOOT_LINES = [
  "loading analyzers · SQG001–007, SQG009",
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
      {/* Deep-space radial behind the matrix — merged tokens, no hardcoded hex. */}
      <div
        className="absolute inset-0 -z-10"
        style={{ background: "radial-gradient(125% 95% at 50% 30%, var(--bg-glow) 0%, var(--bg-deep) 55%, #000000 100%)" }}
      />
      <FallingDotMatrix />

      <div className="relative z-10 flex w-[min(90vw,440px)] flex-col items-center px-6 text-center">
        <motion.div
          initial={reduce ? false : { scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="flex h-14 w-14 items-center justify-center rounded-lg"
          style={{ border: "1px solid var(--line-strong)", background: "var(--surface)" }}
        >
          <ShieldCheck className="h-7 w-7" style={{ color: "var(--accent-cyan)" }} aria-hidden />
        </motion.div>

        <div className="wall-grad-cool mt-4 text-lg font-semibold tracking-[0.2em]">AI SLOP QUARANTINE GUARD</div>
        <div className="wall-label mt-1">Initializing</div>

        <div className="mt-5 h-1 w-full overflow-hidden rounded-full" style={{ background: "var(--line)" }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: "linear-gradient(90deg, var(--accent-violet), var(--accent-cyan))" }}
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ duration, ease: "easeInOut" }}
          />
        </div>

        <ul className="mt-5 w-full space-y-1.5 text-left">
          {BOOT_LINES.map((line, i) => (
            <li
              key={line}
              className="wall-mono flex items-center gap-2 transition-opacity duration-300"
              style={{ opacity: i < step ? 1 : 0.4, color: i < step ? "var(--text)" : "var(--text-faint)" }}
            >
              {i < step ? (
                <Check className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--accent-green)" }} aria-hidden />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--text-faint)" }} aria-hidden />
              )}
              {line}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
