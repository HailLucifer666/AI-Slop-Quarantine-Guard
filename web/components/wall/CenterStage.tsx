"use client"

import dynamic from "next/dynamic"
import { useEffect, useState } from "react"
import { Github, Pause, Play, Settings } from "lucide-react"

import type { WallData } from "@/lib/useWallData"
import { GlobeStatic } from "./GlobeStatic"
import { useReducedMotion } from "./useReducedMotion"

const GlobeCore = dynamic(() => import("./GlobeCore"), {
  ssr: false,
  loading: () => <div className="h-full w-full" />,
})

/** WebGL capability — checked once after mount (spec §6.2): a missing API or a
 * failed context creation renders the static SVG frame instead of a dead canvas.
 * Checked in an effect (not the state initializer) so the server render and the
 * client's first render agree (no hydration mismatch). */
function webglAvailable(): boolean {
  try {
    if (!window.WebGLRenderingContext) return false
    const c = document.createElement("canvas")
    return !!(c.getContext("webgl2") ?? c.getContext("webgl"))
  } catch {
    return false
  }
}

/**
 * Center — the globe is the ONE persistent centerpiece. The earth is a
 * decorative brand backdrop (canvas aria-hidden); the orbit legend captions it,
 * and Recent Scans is the keyboard/screen-reader twin for ring interactions.
 * Overlays: legend (top-left), brand (top-right → home), gear (bottom-left →
 * Settings), interval/pause (bottom-right). All icon buttons 44px hit.
 */
export function CenterStage({
  data,
  paused,
  onTogglePause,
  intervalSec,
  onHome,
  onSettings,
  onOpenScan,
}: {
  data: WallData
  paused: boolean
  onTogglePause: () => void
  intervalSec: number
  onHome: () => void
  onSettings: () => void
  onOpenScan: (id: number) => void
}) {
  const reduced = useReducedMotion()
  const [webgl, setWebgl] = useState<boolean | null>(null)
  useEffect(() => setWebgl(webglAvailable()), [])
  const useStatic = reduced || webgl === false

  return (
    <div className="relative min-h-0 flex-1">
      {/* The canvas is decorative to ATs — Recent Scans is the interactive twin. */}
      <p className="sr-only">
        Live globe of recent scans. The keyboard-accessible list of scans is in the Recent Scans panel.
      </p>

      <div className="absolute inset-0" aria-hidden>
        {useStatic ? (
          <GlobeStatic targets={data.recentTargets} />
        ) : (
          <GlobeCore nodes={data.globe} targets={data.recentTargets} paused={paused} onOpenScan={onOpenScan} />
        )}
      </div>

      {/* Orbit legend — top-left (replaces the retired "Findings Today" hero). */}
      <div className="wall-ring-legend absolute left-1 top-1 z-10 max-w-[62%]">
        {data.recentTargets.length === 0
          ? "Orbits appear after your first scan."
          : `Orbits = last ${data.recentTargets.length} scans · click a ring to open it`}
      </div>

      {/* Brand — top-right → home. 44px hit, 24px visual. */}
      <button onClick={onHome} aria-label="Home" className="wall-focus absolute right-1 top-1 z-10 flex h-11 w-11 items-center justify-center">
        <Github className="h-6 w-6" style={{ color: "var(--text-muted)" }} aria-hidden />
      </button>

      {/* Gear — bottom-left → settings. 44px hit, 16px visual. */}
      <button onClick={onSettings} aria-label="Settings" className="wall-focus absolute bottom-1 left-1 z-10 flex h-11 w-11 items-center justify-center">
        <Settings className="h-4 w-4" style={{ color: "var(--text-muted)" }} aria-hidden />
      </button>

      {/* Interval + pause — bottom-right. 44px hit on the toggle. */}
      <div className="wall-sub absolute bottom-1 right-1 z-10 flex items-center gap-2">
        <span className="wall-num">{intervalSec} sec</span>
        <button onClick={onTogglePause} aria-label={paused ? "Resume" : "Pause"} className="wall-focus flex h-11 w-11 items-center justify-center">
          {paused ? <Play className="h-4 w-4" aria-hidden /> : <Pause className="h-4 w-4" aria-hidden />}
        </button>
      </div>
    </div>
  )
}
