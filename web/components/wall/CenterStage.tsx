"use client"

import dynamic from "next/dynamic"
import { Github, Pause, Play, Settings } from "lucide-react"

import { formatNumber } from "@/lib/format"
import type { WallData } from "@/lib/useWallData"

const GlobeCore = dynamic(() => import("./GlobeCore"), {
  ssr: false,
  loading: () => <div className="h-full w-full" />,
})

/**
 * Center — the globe is the ONE persistent centerpiece (no slideshow). Floating
 * overlays match the reference: headline (top-left → Analyses), brand (top-right
 * → home), gear (bottom-left → Settings), interval/pause (bottom-right).
 */
export function CenterStage({
  data,
  paused,
  onTogglePause,
  intervalSec,
  onOpen,
  onHome,
}: {
  data: WallData
  paused: boolean
  onTogglePause: () => void
  intervalSec: number
  onOpen: (p: "analyses" | "settings") => void
  onHome: () => void
}) {
  return (
    <div className="relative min-h-0 flex-1">
      <div className="absolute inset-0">
        <GlobeCore nodes={data.globe} paused={paused} />
      </div>

      {/* Headline — top-left. */}
      <button onClick={() => onOpen("analyses")} className="wall-click wall-focus absolute left-1 top-1 z-10 text-left">
        <div className="wall-label">Findings Today</div>
        <div className="wall-figure wall-grad-pink mt-1 text-[clamp(2.4rem,4.5vw,4rem)]">{formatNumber(data.slopToday)}</div>
        <div className="mt-1 text-[11px]" style={{ color: "var(--wall-faint)" }}>findings today</div>
      </button>

      {/* Brand — top-right → home. */}
      <button onClick={onHome} aria-label="Home" className="wall-focus absolute right-1 top-1 z-10 opacity-70 transition-opacity hover:opacity-100">
        <Github className="h-6 w-6" style={{ color: "var(--wall-muted)" }} aria-hidden />
      </button>

      {/* Gear — bottom-left → settings. */}
      <button onClick={() => onOpen("settings")} aria-label="Settings" className="wall-focus absolute bottom-1 left-1 z-10 opacity-60 transition-opacity hover:opacity-100">
        <Settings className="h-4 w-4" style={{ color: "var(--wall-muted)" }} aria-hidden />
      </button>

      {/* Interval + pause — bottom-right. */}
      <div className="absolute bottom-1 right-1 z-10 flex items-center gap-2 text-[11px]" style={{ color: "var(--wall-faint)" }}>
        <span className="wall-num">{intervalSec} sec</span>
        <button onClick={onTogglePause} aria-label={paused ? "Resume" : "Pause"} className="wall-focus transition-colors hover:text-[color:var(--wall-text)]">
          {paused ? <Play className="h-4 w-4" aria-hidden /> : <Pause className="h-4 w-4" aria-hidden />}
        </button>
      </div>
    </div>
  )
}
