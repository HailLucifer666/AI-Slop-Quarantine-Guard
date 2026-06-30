"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"

import { formatNumber } from "@/lib/format"
import { useWallData } from "@/lib/useWallData"
import { CenterStage } from "@/components/wall/CenterStage"
import { ContribHeatmap } from "@/components/wall/ContribHeatmap"
import { DataStreamFeed } from "@/components/wall/DataStreamFeed"
import { FindingsSplit } from "@/components/wall/FindingsSplit"
import { RankedPanel } from "@/components/wall/RankedPanel"
import { StatBig } from "@/components/wall/StatBig"
import { RecentScans } from "@/components/wall/panels/RecentScans"
import { EngineTelemetry, FindingsTrend } from "@/components/wall/panels/BottomStats"

const INTERVAL_MS = 15000

/**
 * Command Wall — the cockpit body. The shell (dock, ⌘K palette, .wall-root) lives
 * in AppShell and persists across navigation; this page renders only the cockpit:
 * left rail (stats + trending), center globe, right rail (Data Stream + Recent
 * Scans), bottom strip. Every tile navigates to a dedicated page. Real data only.
 */
export default function DashboardPage() {
  const [paused, setPaused] = useState(false)
  const { data, error, scans, online } = useWallData({ paused, intervalMs: INTERVAL_MS })
  const router = useRouter()
  const [reconnected, setReconnected] = useState(false)
  const wasError = useRef(false)

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

  return (
    <>
      {error && (
        <div className="mx-4 mt-1 rounded-md px-3 py-1.5 text-xs" style={{ color: "var(--wall-act-failed)", background: "rgba(255,59,92,0.07)", border: "1px solid rgba(255,59,92,0.22)" }}>
          {error} — is the API running on :8000?
        </div>
      )}

      {/* TOP REGION */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 px-3 py-2 lg:grid-cols-[300px_minmax(0,1fr)_340px] lg:grid-rows-[minmax(0,1fr)]">
        {/* Left rail */}
        <div className="flex min-h-0 flex-col gap-5 lg:border-r wall-divider lg:pr-3">
          <StatBig label="Repos Scanned" value={formatNumber(data.scanned)} sub={`scanned · ${data.scannedRecent} in last 10 min`} onClick={() => router.push("/analyses")} size="xl" />
          <div className="min-h-0 flex-1 overflow-hidden">
            <RankedPanel checks={data.byCheck} files={data.topFiles} onOpen={(p) => router.push(`/${p}`)} />
          </div>
        </div>

        {/* Center globe */}
        <div className="flex min-h-[55vh] flex-col lg:min-h-0">
          <CenterStage data={data} paused={paused} onTogglePause={() => setPaused((p) => !p)} intervalSec={INTERVAL_MS / 1000} onOpen={(p) => router.push(`/${p}`)} onHome={() => router.push("/dashboard")} />
        </div>

        {/* Right rail: Data Stream + Recent Scans */}
        <div className="flex min-h-0 flex-col gap-4 lg:border-l wall-divider lg:pl-3">
          <div className="min-h-0 flex-1 overflow-hidden">
            <DataStreamFeed feed={data.feed} />
          </div>
          <div className="min-h-0 overflow-hidden" style={{ maxHeight: "42%" }}>
            <RecentScans targets={data.recentTargets} onOpen={(sid) => router.push(`/analyses/${sid}`)} />
          </div>
        </div>
      </div>

      {/* BOTTOM STRIP — four real-data panels (no dead space): findings split,
          findings trend, contribution graph, honest engine telemetry. */}
      <div className="grid shrink-0 grid-cols-2 border-t wall-divider lg:grid-cols-4">
        <button onClick={() => router.push("/analyses")} className="wall-click wall-focus border-r wall-divider px-5 py-4 text-left">
          <FindingsSplit cleanPasses={data.cleanPasses} findings={data.findingsTotal} blockEligible={data.blockEligible} />
        </button>
        <div className="border-r wall-divider px-5 py-4 lg:border-r">
          <FindingsTrend series={data.severitySeries} />
        </div>
        <button onClick={() => router.push("/analyses")} className="wall-click wall-focus border-r wall-divider px-5 py-4 text-left max-lg:border-r-0">
          <ContribHeatmap cells={data.heatmap} />
        </button>
        <div className="px-5 py-4">
          <EngineTelemetry scans={scans} online={online} scannedRecent={data.scannedRecent} />
        </div>
      </div>

      {reconnected && (
        <div role="status" aria-live="polite" className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md px-3 py-1.5 text-xs" style={{ background: "rgba(34,232,232,0.12)", border: "1px solid var(--wall-cyan)", color: "var(--wall-text)" }}>
          Connection restored
        </div>
      )}
    </>
  )
}
