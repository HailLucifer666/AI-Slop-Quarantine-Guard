import { describe, it, expect, beforeEach, vi } from "vitest"

import { derive, type FixFirstRow } from "@/lib/useWallData"
import { FIXTURE_SCANS, FIXTURE_AUDIT } from "./fixtures"

beforeEach(() => {
  vi.setSystemTime(new Date("2026-11-12T06:00:00Z").getTime())
  vi.clearAllMocks()
})

function run(scans: typeof FIXTURE_SCANS, audit: typeof FIXTURE_AUDIT) {
  return { data: derive(scans, audit) }
}

function byId(rows: readonly FixFirstRow[], id: number) {
  return rows.find((r) => r.scanId === id)!
}

describe("derive() — FixFirst ranking contract (design §3.2)", () => {
  it("orders [B, A, F, G, C] when B ties A on block count but is newer", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.fixFirst.map((r) => r.scanId)).toEqual([2, 1, 6, 7, 3])
    expect(data.fixFirst[0].scanId).toBe(2) // B: T-1h, block=3
    expect(data.fixFirst[1].scanId).toBe(1) // A: T-2h, block=3
  })

  it("excludes running scans and scans with null analytics", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.fixFirst.map((r) => r.scanId)).not.toContain(5)
    expect(data.fixFirst.map((r) => r.scanId)).not.toContain(8)
  })

  it("excludes completed scans whose block_eligible is 0", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.fixFirst.map((r) => r.scanId)).not.toContain(4)
  })

  it("advisories = max(0, total_findings - block_eligible)", () => {
    const byId = Object.fromEntries(run(FIXTURE_SCANS, FIXTURE_AUDIT).data.fixFirst.map((r) => [r.scanId, r]))
    expect(byId[2].advisories).toBe(0)
    expect(byId[1].advisories).toBe(1)
  })

  it("caps topChecks at 2, sorted by count desc", () => {
    const b = byId(run(FIXTURE_SCANS, FIXTURE_AUDIT).data.fixFirst, 2)
    expect(b.topChecks.map((c) => c.id)).toEqual(["SQG002", "SQG001"])
    expect(b.topChecks[0].name).toBe("Leaked secret")
  })

  it("caps fixFirst at 5 rows", () => {
    expect(run(FIXTURE_SCANS, FIXTURE_AUDIT).data.fixFirst).toHaveLength(5)
  })

  it("sev is the worst confidence tier", () => {
    const byId = Object.fromEntries(run(FIXTURE_SCANS, FIXTURE_AUDIT).data.fixFirst.map((r) => [r.scanId, r]))
    expect(byId[6].sev).toBe("high")
    expect(byId[3].sev).toBe("medium")
  })

  it("at is epoch ms from created_at", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.fixFirst[0].at).toBe(new Date("2026-11-12T05:00:00.000Z").getTime())
  })

  it("zero block-eligible across all scans -> empty fixFirst", () => {
    const cleanOnly = FIXTURE_SCANS.filter((s) => s.id === 4).map((s) => ({
      ...s, analytics: { ...s.analytics!, block_eligible: 0 },
    }))
    const { data } = run(cleanOnly, [])
    expect(data.fixFirst).toEqual([])
  })
})

describe("derive() — totals and rollups", () => {
  it("sums certain/high/medium across completed scans", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.certainTotal).toBe(5) // G:2 + A:2 + B:1
    expect(data.highTotal).toBe(6) // A:1 + B:2 + F:3
    expect(data.mediumTotal).toBe(2) // A:1 + C:1
  })

  it("incompleteCoverage counts fully_covered === false", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.incompleteCoverage).toBe(1)
  })

  it("latestCompletedId is the max completed id", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.latestCompletedId).toBe(8)
  })

  it("cleanRate rounds cleanPasses/completed", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.cleanRate).toBe(14)
    expect(data.cleanPasses).toBe(1)
  })

  it("blockEligible and findingsTotal are sums", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.blockEligible).toBe(11)
    expect(data.findingsTotal).toBe(13)
  })

  it("scannedRecent counts scans in the last 10 min", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.scannedRecent).toBe(1)
  })
})

describe("derive() — heatmap, series shapes and empty state", () => {
  it("heatmap is exactly 13 weeks (91 cells), newest last", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.heatmap).toHaveLength(91)
    expect(data.heatmap[0].day).toBe("2026-08-14")
    expect(data.heatmap[90].day).toBe("2026-11-12")
    expect(data.heatmap.every((c) => typeof c.count === "number" && !Number.isNaN(c.count))).toBe(true)
  })

  it("heatmap buckets every scan by created day, counts all statuses", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    const byDay = Object.fromEntries(data.heatmap.map((c) => [c.day, c.count]))
    expect(byDay["2026-11-12"]).toBe(8) // A, B, C, D, E, F, G, H all on the same day
    expect(byDay["2026-11-11"]).toBe(0)
    expect(byDay["2026-11-10"]).toBe(0)
  })

  it("severitySeries is chronologic, per-scan certain/high/medium", () => {
    const { data } = run(FIXTURE_SCANS, FIXTURE_AUDIT)
    expect(data.severitySeries).toHaveLength(7)
    // Oldest completed scan is H (null analytics) -> first series entry is 0,0,0
    expect(data.severitySeries[0].certain + data.severitySeries[0].high + data.severitySeries[0].medium).toBe(0)
    // Next is G (CERTAIN:2)
    expect(data.severitySeries[1].certain + data.severitySeries[1].high + data.severitySeries[1].medium).toBe(2)
  })

  it("empty state yields the EMPTY contract with no NaN leaks", () => {
    const { data } = run([], [])
    expect(data.fixFirst).toEqual([])
    expect(data.severitySeries).toEqual([])
    expect(data.byCheck).toEqual([])
    expect(data.heatmap).toEqual([])
    expect(data.globe).toEqual([])
    expect(data.recentTargets).toEqual([])
    expect(data.latestCompletedId).toBeNull()
    expect(data.trustStatus).toBe("green")
    expect(data.certainTotal).toBe(0)
    expect(data.highTotal).toBe(0)
    expect(data.mediumTotal).toBe(0)
    expect(data.blockEligible).toBe(0)
    expect(data.findingsTotal).toBe(0)
    expect(data.slopToday).toBe(0)
    expect(data.scannedRecent).toBe(0)
    expect(data.scanned).toBe(0)
    expect(data.completed).toBe(0)
    expect(data.cleanRate).toBe(100)
  })
})
