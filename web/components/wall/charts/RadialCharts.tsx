"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"

import { useReducedMotion } from "@/components/wall/useReducedMotion"

/**
 * Lightweight SVG radial charts for the scan result view — no chart dependency.
 * `Donut` renders proportional segments (severity / per-rule); `RingGauge` renders
 * a single-value coverage arc. Both fade+scale in and count up their center value;
 * `prefers-reduced-motion` renders them static. Every value is real analytics —
 * nothing is fabricated.
 */
export interface Segment {
  label: string
  value: number
  color: string
}

/** Count 0 → value over ~0.8s (instant when reduced-motion). */
function useCountUp(value: number): number {
  const reduced = useReducedMotion()
  const [n, setN] = useState(reduced ? value : 0)
  const ref = useRef(0)
  useEffect(() => {
    if (reduced) {
      setN(value)
      return
    }
    let raf = 0
    const start = ref.current
    let t0: number | null = null
    const step = (ts: number) => {
      if (t0 === null) t0 = ts
      const p = Math.min(1, (ts - t0) / 600)
      const eased = 1 - Math.pow(1 - p, 3)
      const cur = Math.round(start + (value - start) * eased)
      setN(cur)
      ref.current = cur
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value, reduced])
  return n
}

const SIZE = 150
const STROKE = 15
const R = (SIZE - STROKE) / 2
const CX = SIZE / 2
const C = 2 * Math.PI * R

function Frame({ children, label }: { children: React.ReactNode; label: string }) {
  const reduced = useReducedMotion()
  return (
    <motion.div
      className="flex flex-col items-center gap-2"
      initial={reduced ? false : { opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <div className="relative" style={{ width: SIZE, height: SIZE }}>{children}</div>
      <div className="text-xs" style={{ color: "var(--text-faint)" }}>{label}</div>
    </motion.div>
  )
}

function Center({ value, sub }: { value: number; sub: string }) {
  const n = useCountUp(value)
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center">
      <span className="wall-num text-3xl leading-none" style={{ color: "var(--text)" }}>{n}</span>
      <span className="mt-1 text-xs" style={{ color: "var(--text-faint)" }}>{sub}</span>
    </div>
  )
}

/** Proportional segmented donut. Empty (all-zero) → a calm full green ring. */
export function Donut({ title, segments, centerSub }: { title: string; segments: Segment[]; centerSub: string }) {
  const total = segments.reduce((s, x) => s + x.value, 0)
  let cum = 0
  return (
    <Frame label={title}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${title}: ${total}`}>
        <g transform={`rotate(-90 ${CX} ${CX})`}>
          <circle cx={CX} cy={CX} r={R} fill="none" stroke="var(--line)" strokeWidth={STROKE} />
          {total === 0 ? (
            <circle cx={CX} cy={CX} r={R} fill="none" stroke="var(--sev-clean)" strokeWidth={STROKE} opacity={0.5} />
          ) : (
            segments
              .filter((s) => s.value > 0)
              .map((s) => {
                const frac = s.value / total
                const dash = Math.max(0, frac * C - 1.5) // tiny gap between segments
                const off = -cum * C
                cum += frac
                return (
                  <circle
                    key={s.label}
                    cx={CX}
                    cy={CX}
                    r={R}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={STROKE}
                    strokeDasharray={`${dash} ${C}`}
                    strokeDashoffset={off}
                    strokeLinecap="butt"
                  />
                )
              })
          )}
        </g>
      </svg>
      <Center value={total} sub={centerSub} />
    </Frame>
  )
}

/** Single-value coverage ring (e.g. files scanned vs skipped). */
export function RingGauge({ title, value, max, color, centerSub }: { title: string; value: number; max: number; color: string; centerSub: string }) {
  const frac = max > 0 ? Math.min(1, value / max) : 1
  return (
    <Frame label={title}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${title}: ${value} of ${max}`}>
        <g transform={`rotate(-90 ${CX} ${CX})`}>
          <circle cx={CX} cy={CX} r={R} fill="none" stroke="var(--line)" strokeWidth={STROKE} />
          <motion.circle
            cx={CX}
            cy={CX}
            r={R}
            fill="none"
            stroke={color}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={`${frac * C} ${C}`}
            initial={false}
          />
        </g>
      </svg>
      <Center value={value} sub={centerSub} />
    </Frame>
  )
}
