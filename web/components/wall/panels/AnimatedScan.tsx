"use client"

import { useEffect, useState } from "react"
import { ChevronDown } from "lucide-react"
import { motion, useReducedMotion } from "framer-motion"

import type { ScanProgress, ScanStatus } from "@/lib/types"

/**
 * Scan progress HUD — a faithful re-skin of the reference "download" mockup:
 * a notched status tag with stacked chevrons, a full-width hairline, a 3-column
 * mono readout (PROGRESS capsule bar · ELAPSED · FILES SCANNED), and a closing
 * hairline. Monochrome / JetBrains-Mono to match the mockup.
 *
 * Honest by construction: PROGRESS is the real analyzer phase index/total (no
 * invented %), ELAPSED is a real timer (the mockup's "EST. TIME" is dropped — we
 * never fabricate an ETA), FILES is the real running count.
 */
const PHASE_LABEL: Record<string, string> = {
  cloning: "Downloading repository",
  reading: "Reading files",
  analyzing: "Starting analysis",
  dependencies: "Hallucinated packages",
  placeholders: "Placeholder code",
  secrets: "Leaked secrets",
  vulnerabilities: "Vulnerable dependencies",
  sast: "Security issues",
  licenses: "Risky licenses",
  typosquat: "Typosquat check",
  simplify: "Simplification pass",
  reporting: "Compiling report",
}

// A running scan whose heartbeat has been quiet longer than this is not "slow" —
// say so, well before the server's 300s stale-lease reap marks it failed.
const STALE_HEARTBEAT_SECONDS = 90

const TAG_CLIP = "polygon(0 0, calc(100% - 11px) 0, 100% 50%, calc(100% - 11px) 100%, 0 100%)"

function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

export function AnimatedScan({
  status = "idle",
  progress,
  startedAt,
  filesScanned,
  queuePosition,
  heartbeatAt,
  active,
}: {
  status?: ScanStatus | "idle"
  progress?: ScanProgress | null
  startedAt?: string | null
  filesScanned?: number | null
  /** How many queued scans precede this one (API sets it only while queued). */
  queuePosition?: number | null
  /** Liveness lease the API already returns — read here so stuck-vs-slow is visible. */
  heartbeatAt?: string | null
  active: boolean
}) {
  const reduce = useReducedMotion()
  const [now, setNow] = useState(() => Date.now())

  // Tick while the scan is queued or running even if `active` has been dropped by
  // the console (a capped poll must not freeze the elapsed clock on a live scan).
  const live = active || status === "queued" || status === "running"
  useEffect(() => {
    if (!live) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [live])

  const started = startedAt ? new Date(startedAt).getTime() : null
  const failed = status === "failed"
  const done = status === "completed"
  const determinate = !!progress && progress.total > 0
  // The running phase is the active step (1-based): the backend emits `index` as the
  // count of analyzers already finished, so the phase being shown is index+1. Driving the
  // bar, the step number, and the phase label all off `step` keeps them in agreement — the
  // bar leaves 0 on the first phase and reaches 100% at the final one. min() clamps the
  // closing `reporting` event (index === total) back to total/total instead of overshooting.
  const step = determinate ? Math.min(progress!.index + 1, progress!.total) : 0
  const pct = determinate ? Math.round((step / progress!.total) * 100) : done ? 100 : 0
  const accent = failed ? "var(--sev-certain)" : done ? "var(--accent-green)" : "var(--text)"

  const statusWord =
    status === "idle" ? "Ready"
      : status === "queued" ? "Queued"
      : failed ? "Failed"
      : done ? "Complete"
      : "Analysing"

  const queuedCaption =
    queuePosition != null && queuePosition > 0
      ? `Queued · ${queuePosition} ahead`
      : "Queued · next up"
  const heartbeatAgeS = heartbeatAt
    ? Math.max(0, Math.floor((now - new Date(heartbeatAt).getTime()) / 1000))
    : null
  const stale = status === "running" && heartbeatAgeS != null && heartbeatAgeS > STALE_HEARTBEAT_SECONDS
  const baseCaption = determinate
    ? `${PHASE_LABEL[progress!.phase] ?? progress!.phase} · ${step}/${progress!.total}`
    : status === "queued"
      ? queuedCaption
      : progress?.phase
        ? (PHASE_LABEL[progress.phase] ?? progress.phase)
        : active
          ? "Starting…"
          : "—"
  const phaseCaption = stale
    ? heartbeatAgeS! < 120
      ? `No heartbeat for ${heartbeatAgeS}s — worker may be stuck`
      : `No heartbeat for ${Math.floor(heartbeatAgeS! / 60)}m — worker may be stuck`
    : baseCaption

  const files = progress?.files_total ?? filesScanned ?? null

  return (
    <div className="font-mono">
      {/* Status tag + stacked chevrons */}
      <div className="flex items-center gap-2.5">
        <div className="flex flex-col" style={{ color: accent }} aria-hidden>
          <motion.span animate={active && !reduce ? { y: [0, 2, 0], opacity: [0.5, 1, 0.5] } : { opacity: 0.6 }} transition={{ duration: 1.2, repeat: active && !reduce ? Infinity : 0 }}>
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.5} />
          </motion.span>
          <ChevronDown className="-mt-2 h-3.5 w-3.5 opacity-50" strokeWidth={2.5} />
        </div>
        <div className="relative inline-flex">
          <span aria-hidden className="absolute inset-0" style={{ background: accent, clipPath: TAG_CLIP }} />
          <span aria-hidden className="absolute" style={{ inset: 1.5, background: "var(--bg-deep)", clipPath: TAG_CLIP }} />
          <span className="relative flex items-center gap-2 py-1 pl-3 pr-6 text-xs font-semibold" style={{ color: accent }}>
            {active && !reduce && <motion.span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: accent }} animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 1.1, repeat: Infinity }} />}
            {statusWord}
          </span>
        </div>
      </div>

      {/* Top hairline */}
      <div className="mt-3 h-px w-full" style={{ background: "var(--text)", opacity: 0.85 }} />

      {/* 3-column readout */}
      <div className="mt-3 grid grid-cols-3 items-start gap-5">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs" style={{ color: "var(--text-faint)" }}>Progress</span>
          {/* Capsule bar */}
          <div className="relative h-2 w-full overflow-hidden rounded-full" style={{ border: "1px solid var(--text)", opacity: 0.95 }}>
            {determinate || done ? (
              <motion.div className="h-full rounded-full" style={{ background: accent }} initial={false} animate={{ width: `${pct}%` }} transition={{ duration: reduce ? 0 : 0.3 }} />
            ) : active && !reduce ? (
              <motion.div className="absolute top-0 h-full w-1/3 rounded-full" style={{ background: "var(--text)", opacity: 0.85 }} animate={{ x: ["-110%", "330%"] }} transition={{ duration: 1.3, repeat: Infinity, ease: "easeInOut" }} />
            ) : null}
          </div>
          <span className="truncate text-xs" style={{ color: "var(--text-muted)" }}>{phaseCaption}</span>
        </div>

        <Readout label="Elapsed" value={started ? fmtElapsed(now - started) : "0:00"} />
        <Readout label="Files scanned" value={files != null ? String(files) : "—"} />
      </div>

      {/* Bottom hairline */}
      <div className="mt-3 h-px w-full" style={{ background: "var(--text)", opacity: 0.85 }} />
    </div>
  )
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs" style={{ color: "var(--text-faint)" }}>{label}</span>
      <span className="wall-num text-sm" style={{ color: "var(--text)" }}>{value}</span>
    </div>
  )
}
