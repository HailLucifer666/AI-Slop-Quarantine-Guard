import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"

import { AnimatedScan } from "@/components/wall/panels/AnimatedScan"

const cloneProgress = { phase: "cloning", index: 0, total: 0, findings_so_far: 0, files_total: null }
const analyzerProgress = { phase: "secrets", index: 2, total: 8, findings_so_far: 1, files_total: 1408 }

describe("AnimatedScan — queued and phase honesty", () => {
  it("a queued scan says its position instead of Starting…", () => {
    // Scans 21/22 both read as hangs: "Analysing" with no queue context while the
    // worker was serial. A queued scan must say where it stands in line.
    render(
      <AnimatedScan status="queued" progress={null} startedAt={new Date().toISOString()} queuePosition={2} active />
    )
    expect(screen.getByText("Queued · 2 ahead")).toBeTruthy()
  })

  it("next-up says so", () => {
    render(
      <AnimatedScan status="queued" progress={null} startedAt={new Date().toISOString()} queuePosition={0} active />
    )
    expect(screen.getByText("Queued · next up")).toBeTruthy()
  })

  it("cloning phase renders its label even while indeterminate", () => {
    // The cloning window has no analyzer index/total — the caption must still say
    // what the scanner is doing rather than falling back to "Starting…".
    render(<AnimatedScan status="running" progress={cloneProgress} startedAt={new Date().toISOString()} active />)
    expect(screen.getByText("Downloading repository")).toBeTruthy()
  })

  it("analyzer phases keep the step/total caption", () => {
    render(<AnimatedScan status="running" progress={analyzerProgress} startedAt={new Date().toISOString()} active />)
    expect(screen.getByText("Leaked secrets · 3/8")).toBeTruthy()
  })

  it("a running scan with a quiet heartbeat says so", () => {
    // Stuck-vs-slow: heartbeat_at was returned by the API and read by nobody. A
    // running scan whose heartbeat went quiet >90s must say so — before the
    // server's 300s stale-lease reap marks it failed.
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    render(
      <AnimatedScan
        status="running"
        progress={analyzerProgress}
        startedAt={new Date().toISOString()}
        heartbeatAt={fiveMinAgo}
        active
      />
    )
    expect(screen.getByText(/No heartbeat for 5m/)).toBeTruthy()
  })

  it("a fresh heartbeat says nothing about being stuck", () => {
    render(
      <AnimatedScan
        status="running"
        progress={analyzerProgress}
        startedAt={new Date().toISOString()}
        heartbeatAt={new Date().toISOString()}
        active
      />
    )
    expect(screen.queryByText(/No heartbeat/)).toBeNull()
  })
})
