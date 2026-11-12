"use client"

import { useEffect, useRef } from "react"

import { CHECKS, RULE_IDS } from "@/lib/checks"
import { useReducedMotion } from "@/components/wall/useReducedMotion"

/**
 * Live Activity Spectrum (ditto Activity-Horizontal.jpg) — one neon lane per
 * check; vertical-bar bursts stream/glow while a scan runs, and settle to the
 * real per-rule finding load on completion. Canvas + rAF, DPR-aware, reduced-
 * motion → static. Never fakes progress: `active` = the real running status.
 */
// One lane per registered check, colours matching the scan-result strip. Derived from
// RULE_IDS so a new rule gets a lane rather than being dropped from the display.
const LANE_COLOR: Record<string, string> = {
  SQG001: "#ff3d8b", SQG002: "#ff3b5c", SQG003: "#ffc83d", SQG004: "#ff8a3d",
  SQG005: "#8b5cf6", SQG006: "#16e0e0", SQG007: "#4d7cff", SQG009: "#5ef08a",
}
const LANES: { id: string; color: string }[] = RULE_IDS.map((id) => ({
  id,
  color: LANE_COLOR[id] ?? "#6f7890", // canvas can't read CSS vars — hex mirror of --text-faint
}))

function noise(n: number): number {
  return Math.abs(Math.sin(n * 12.9898) * 43758.5453) % 1
}

export function ActivitySpectrum({ active, counts }: { active: boolean; counts: Record<string, number> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const reduced = useReducedMotion()
  const max = Math.max(1, ...LANES.map((l) => counts[l.id] ?? 0))

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let raf = 0
    let t = 0

    const resize = () => {
      const r = canvas.getBoundingClientRect()
      canvas.width = Math.max(1, r.width * dpr)
      canvas.height = Math.max(1, r.height * dpr)
    }
    resize()
    // Redraw a single frame on resize so an idle (non-animating) canvas stays painted.
    const ro = new ResizeObserver(() => { resize(); draw() })
    ro.observe(canvas)

    const draw = () => {
      const w = canvas.width
      const h = canvas.height
      ctx.clearRect(0, 0, w, h)
      const laneH = h / LANES.length
      const barW = 3 * dpr
      const gap = 7 * dpr
      const n = Math.floor(w / (barW + gap))
      for (let i = 0; i < LANES.length; i++) {
        const lane = LANES[i]
        const cy = laneH * (i + 0.5)
        const cnt = counts[lane.id] ?? 0
        const settled = cnt / max
        ctx.save()
        ctx.shadowBlur = 12 * dpr
        ctx.shadowColor = lane.color
        ctx.fillStyle = lane.color
        for (let b = 0; b < n; b++) {
          const x = b * (barW + gap)
          const ph = active ? noise(b * 1.7 + Math.floor(t * 0.3) + i * 10) : noise(b * 1.7 + i * 10)
          // idle empty lanes still gently "breathe" so the panel never reads dead.
          const breathe = 0.1 + 0.08 * (0.5 + 0.5 * Math.sin(t * 0.035 + i + b * 0.25))
          const amp = active ? (0.35 + 0.65 * ph) * (0.6 + 0.4 * Math.sin(t * 0.06 + i)) : cnt > 0 ? settled * ph : breathe
          const bh = Math.max(2 * dpr, amp * laneH * 0.82)
          ctx.globalAlpha = active ? 0.3 + 0.6 * ph : cnt > 0 ? 0.25 + 0.65 * ph : 0.1 + 0.1 * (0.5 + 0.5 * Math.sin(t * 0.03 + i))
          ctx.fillRect(x, cy - bh / 2, barW, bh)
        }
        ctx.restore()
      }
      t += 1
      // Only animate while a scan is running. When idle/completed the bars are
      // already settled to real counts — stop scheduling frames so the loop can't
      // pin the main thread (and freeze nav) after a large scan finishes.
      if (active && !reduced && !document.hidden) raf = requestAnimationFrame(draw)
    }

    // Pause the loop when the tab is hidden; kick a fresh frame when it returns.
    const onVisible = () => {
      cancelAnimationFrame(raf)
      if (active && !reduced && !document.hidden) raf = requestAnimationFrame(draw)
    }
    document.addEventListener("visibilitychange", onVisible)

    draw()
    if (active && !reduced && !document.hidden) raf = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [active, counts, reduced, max])

  return (
    <div className="flex h-full w-full gap-5">
      {/* Each row is flex-1 so it centers within its 1/N height band — matching the
          canvas lane centers at (i+0.5)·h/N, so every label lines up with its lane. */}
      <div className="flex shrink-0 flex-col">
        {LANES.map((l) => (
          <div key={l.id} className="flex flex-1 items-center gap-2.5 text-sm" style={{ color: "var(--text-muted)" }}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color, boxShadow: `0 0 8px ${l.color}` }} aria-hidden />
            <span className="w-44 whitespace-nowrap">{CHECKS[l.id]?.name ?? l.id}</span>
            <span className="wall-num" style={{ color: "var(--text)" }}>{counts[l.id] ?? 0}</span>
          </div>
        ))}
      </div>
      <canvas ref={canvasRef} className="block h-full min-h-0 min-w-0 flex-1" aria-hidden />
    </div>
  )
}
