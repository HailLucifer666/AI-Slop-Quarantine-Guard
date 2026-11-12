"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"

import { useWallData } from "@/lib/useWallData"
import { useCountUp, useDelayedFlag } from "@/components/wall/hooks"
import { useReducedMotion } from "@/components/wall/useReducedMotion"
import { CenterStage } from "@/components/wall/CenterStage"
import { ContribHeatmap } from "@/components/wall/ContribHeatmap"
import { DataStreamFeed } from "@/components/wall/DataStreamFeed"
import { FindingsSplit } from "@/components/wall/FindingsSplit"
import { FixFirst } from "@/components/wall/FixFirst"
import { Hero } from "@/components/wall/Hero"
import { RankedPanel } from "@/components/wall/RankedPanel"
import { RecentScans } from "@/components/wall/panels/RecentScans"
import { EngineTelemetry, FindingsTrend } from "@/components/wall/panels/BottomStats"

const INTERVAL_MS = 15000

/** Loading placeholder — mounted ONLY after the 300ms delayed flag (spec §7):
 * a fast API response never flashes skeletons. */
function SkeletonBoard() {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 px-3 py-2 lg:grid-cols-[300px_minmax(0,1fr)_340px]" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex flex-col gap-2">
          <div className="wall-skeleton h-3 w-3/4" />
          <div className="wall-skeleton h-3 w-1/2" />
          <div className="wall-skeleton h-8 w-full" />
        </div>
      ))}
    </div>
  )
}

/**
 * Command Wall — the cockpit body. The shell (dock, ⌘K palette, .wall-root) lives
 * in AppShell and persists across navigation; this page renders only the cockpit:
 * hero (quarantine status) → FixFirst → center globe → Data Stream + Recent Scans
 * → Most Flagged, then the bottom strip. DOM order = mobile visual order (§8);
 * named grid areas rearrange it on desktop. Every tile navigates to a dedicated
 * page. Real data only.
 */
export default function DashboardPage() {
  const [paused, setPaused] = useState(false)
  const { data, error, scans, online, loading } = useWallData({ paused, intervalMs: INTERVAL_MS })
  const router = useRouter()
  const [reconnected, setReconnected] = useState(false)
  const wasError = useRef(false)
  const reduced = useReducedMotion()

  // Announce reconnection when the API recovers from an outage.
  useEffect(() => {
    const prev = wasError.current
    wasError.current = !!error
    if (prev && !error) {
      setReconnected(true)
      const t = setTimeout(() => setReconnected(false), 3000)
      return () => clearTimeout(t)
    }
  }, [error])

  // THE signature moment — scan-complete beam sweep (spec §10.4): fires exactly
  // once when latestCompletedId changes from one non-null value to a new one;
  // never under reduced motion; completions while the tab is hidden coalesce to
  // one sweep on return.
  const [sweeping, setSweeping] = useState(false)
  const prevCompletedId = useRef<number | null>(null)
  const pendingSweep = useRef(false)
  const sweepTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fireSweep = useCallback(() => {
    setSweeping(true)
    if (sweepTimer.current) clearTimeout(sweepTimer.current)
    sweepTimer.current = setTimeout(() => setSweeping(false), 750)
  }, [])

  useEffect(() => {
    const cur = data.latestCompletedId
    const prev = prevCompletedId.current
    prevCompletedId.current = cur
    if (cur == null || prev == null || prev === cur || reduced) return
    if (typeof document !== "undefined" && document.hidden) {
      pendingSweep.current = true
      return
    }
    fireSweep()
  }, [data.latestCompletedId, reduced, fireSweep])

  useEffect(() => {
    const onVis = () => {
      if (!document.hidden && pendingSweep.current) {
        pendingSweep.current = false
        if (!reduced) fireSweep()
      }
    }
    document.addEventListener("visibilitychange", onVis)
    return () => document.removeEventListener("visibilitychange", onVis)
  }, [reduced, fireSweep])

  useEffect(() => () => {
    if (sweepTimer.current) clearTimeout(sweepTimer.current)
  }, [])

  const skeleton = useDelayedFlag(loading, 300)
  // Count-up applies to the hero percentage and the Findings Caught tile figure.
  const animatedFindings = useCountUp(data.findingsTotal)

  return (
    <>
      {error && (
        <div
          role="alert"
          className="mx-4 mt-1 rounded-md border px-3 py-1.5 text-xs"
          style={{ color: "var(--sev-certain)", background: "rgba(255,59,92,0.07)", borderColor: "rgba(255,59,92,0.22)" }}
        >
          {error} — is the API running on :8000?
        </div>
      )}

      {skeleton ? (
        <>
          <span className="sr-only">Loading live data…</span>
          <SkeletonBoard />
        </>
      ) : (
        <>
          {/* TOP REGION — named grid areas (spec §2a.1): hero+fix+most = left rail
              (300px), center = globe, stream = right rail (340px). DOM order is the
              mobile stack order; no `order` tricks. */}
          <div className="relative grid min-h-0 flex-1 grid-cols-1 gap-3 px-3 py-2 lg:[grid-template-areas:'hero_center_stream''fix_center_stream''most_center_stream'] lg:grid-cols-[300px_minmax(0,1fr)_340px] lg:grid-rows-[auto_auto_minmax(0,1fr)]">
            {/* Continuous rail hairlines (desktop only; mid-gap of each column). */}
            <div aria-hidden className="wall-rail-line hidden lg:left-[318px] lg:block" />
            <div aria-hidden className="wall-rail-line hidden lg:right-[358px] lg:block" />

            <section className="min-w-0 lg:[grid-area:hero]">
              <Hero
                rate={data.cleanRate}
                cleanPasses={data.cleanPasses}
                completed={data.completed}
                blockEligible={data.blockEligible}
                highTotal={data.highTotal}
                mediumTotal={data.mediumTotal}
                incompleteCoverage={data.incompleteCoverage}
                scannedRecent={data.scannedRecent}
                onOpen={() => router.push("/analyses")}
              />
            </section>

            <section className="min-w-0 lg:[grid-area:fix]">
              <FixFirst rows={data.fixFirst} completed={data.completed} />
            </section>

            {/* Globe banner on mobile: 40vh (min 320px); full center column on lg. */}
            <section className="flex h-[40vh] min-h-[320px] min-w-0 flex-col lg:h-auto lg:min-h-0 lg:[grid-area:center]">
              <CenterStage
                data={data}
                paused={paused}
                onTogglePause={() => setPaused((p) => !p)}
                intervalSec={INTERVAL_MS / 1000}
                onHome={() => router.push("/dashboard")}
                onSettings={() => router.push("/settings")}
                onOpenScan={(id) => router.push(`/analyses/${id}`)}
              />
            </section>

            <section className="flex min-h-0 min-w-0 flex-col gap-4 lg:[grid-area:stream]">
              <div className="min-h-0 flex-1 overflow-hidden">
                <DataStreamFeed feed={data.feed} />
              </div>
              <div className="min-h-0 overflow-hidden lg:max-h-[42%]">
                <RecentScans targets={data.recentTargets} onOpen={(sid) => router.push(`/analyses/${sid}`)} />
              </div>
            </section>

            <section className="min-h-0 min-w-0 overflow-hidden lg:[grid-area:most]">
              <RankedPanel checks={data.byCheck} files={data.topFiles} onOpen={(p) => router.push(`/${p}`)} />
            </section>
          </div>

          {/* BOTTOM STRIP — findings split / trend / heatmap / honest engine
              telemetry. 1 col < 768px → 2 at md → 4 at lg; horizontal dividers
              only between stacked tiles. */}
          <div className="grid shrink-0 grid-cols-1 border-t wall-divider md:grid-cols-2 lg:grid-cols-4">
            <button onClick={() => router.push("/analyses")} className="wall-click wall-focus border-b wall-divider px-5 py-4 text-left md:border-r lg:border-b-0">
              <FindingsSplit cleanPasses={data.cleanPasses} findings={animatedFindings} blockEligible={data.blockEligible} />
            </button>
            <div className="border-b wall-divider px-5 py-4 lg:border-b-0 lg:border-r">
              <FindingsTrend series={data.severitySeries} />
            </div>
            <button onClick={() => router.push("/analyses")} className="wall-click wall-focus border-b wall-divider px-5 py-4 text-left md:border-b-0 md:border-r">
              <ContribHeatmap cells={data.heatmap} scanned={data.scanned} />
            </button>
            <div className="px-5 py-4">
              <EngineTelemetry scans={scans} online={online} scannedRecent={data.scannedRecent} />
            </div>
          </div>
        </>
      )}

      {sweeping && <div className="wall-sweep" aria-hidden />}

      {reconnected && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md border px-3 py-1.5 text-xs"
          style={{ background: "rgba(22,224,224,0.12)", borderColor: "var(--accent-cyan)", color: "var(--text)" }}
        >
          Connection restored
        </div>
      )}
    </>
  )
}
