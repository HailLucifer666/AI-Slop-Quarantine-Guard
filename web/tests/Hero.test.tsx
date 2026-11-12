import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"

import { Hero } from "@/components/wall/Hero"

/**
 * Regression for the quarantine-status honesty bug (build-pr review): the hero's
 * "All clean" branch used to key off the ROUNDED rate (rate === 100) — at ≥200
 * completed scans with exactly one unclean scan, Math.round((199/200)*100) === 100
 * and the hero falsely claimed "All 200 scans came back clean." The fix branches
 * on the actual count: allClean = completed > 0 && cleanPasses === completed
 * (page.tsx:59). These tests pin that boundary at both edges plus the zero state.
 *
 * The figure is useCountUp-animated (RAF in jsdom), so assertions target the
 * static statement paragraph — except completed === 0, where the figure renders
 * the literal "—" with no animation.
 */
const base = {
  blockEligible: 0,
  highTotal: 0,
  mediumTotal: 0,
  incompleteCoverage: 0,
  scannedRecent: 0,
  onOpen: () => {},
}

describe("Hero — quarantine status honesty (rate-rounding regression)", () => {
  it("199/200 (rate rounds to 100) states '199 of 200', never 'All 200 scans came back clean.'", () => {
    const { container } = render(
      <Hero rate={100} cleanPasses={199} completed={200} {...base} />,
    )
    expect(screen.getByText("199 of 200 scans came back clean.")).toBeTruthy()
    expect(screen.queryByText(/All 200 scans came back clean/)).toBeNull()
    // ShieldAlert (risk) instead of ShieldCheck (all-clear) at this boundary.
    expect(container.querySelector("svg.lucide-shield-alert")).toBeTruthy()
    expect(container.querySelector("svg.lucide-shield-check")).toBeNull()
  })

  it("200/200 states 'All 200 scans came back clean.'", () => {
    const { container } = render(
      <Hero rate={100} cleanPasses={200} completed={200} {...base} />,
    )
    expect(screen.getByText("All 200 scans came back clean.")).toBeTruthy()
    expect(container.querySelector("svg.lucide-shield-check")).toBeTruthy()
    expect(container.querySelector("svg.lucide-shield-alert")).toBeNull()
  })

  it("no scans yet: honest 'No scans yet' copy, a '—' figure, and the neutral Shield", () => {
    const { container } = render(
      <Hero rate={0} cleanPasses={0} completed={0} {...base} />,
    )
    expect(screen.getByText(/No scans yet/)).toBeTruthy()
    // completed === 0 renders the literal em dash — no count-up to race.
    expect(container.querySelector(".wall-figure-hero")!.textContent).toBe("—")
    expect(container.querySelector("svg.lucide-shield")).toBeTruthy()
  })
})
