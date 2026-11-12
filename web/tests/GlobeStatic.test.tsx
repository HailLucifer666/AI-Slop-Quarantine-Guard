import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"

import { GlobeStatic } from "@/components/wall/GlobeStatic"
import type { RecentTarget } from "@/lib/useWallData"
import { mkRecentTarget } from "./fixtures"

describe("GlobeStatic — reduced-motion / no-WebGL fallback", () => {
  it("renders focusable ring links with aria-labels from fixture RecentTargets", () => {
    const targets: RecentTarget[] = [
      mkRecentTarget(1, "https://github.com/acarg/secret-leaker", "completed", false, 3, "certain", 5100),
      mkRecentTarget(2, "https://github.com/acarg/clean-project", "completed", true, 0, "clean", 80),
      mkRecentTarget(3, "https://github.com/acarg/running-scan", "running", false, 0, "high", 0),
    ]
    const { container } = render(<GlobeStatic targets={targets} />)
    const links = container.querySelectorAll("a")
    expect(links.length).toBe(3)
    const first = links[0]
    expect(first.getAttribute("href")).toBe("/analyses/1")
    const label = first.getAttribute("aria-label") ?? ""
    expect(label).toContain("secret-leaker")
    expect(label).toContain("completed")
    expect(label).toContain("5100 files")
    // Each ring wraps a real ellipse (the focusable orbit).
    expect(first.querySelector("ellipse")).toBeTruthy()
  })

  it("empty state when there are no scans", () => {
    render(<GlobeStatic targets={[]} />)
    expect(screen.getByText(/Orbits appear after your first scan/)).toBeTruthy()
    expect(document.querySelectorAll("a").length).toBe(0)
  })

  it("renders the orbit legend caption", () => {
    const targets: RecentTarget[] = [
      mkRecentTarget(1, "x", "completed", false, 3, "certain", 5100),
      mkRecentTarget(2, "y", "completed", true, 0, "clean", 80),
    ]
    render(<GlobeStatic targets={targets} />)
    expect(screen.getByText(/Orbits = last 2 scans/)).toBeTruthy()
  })

  it("ring colors honor the status contract (clean=green, failed=crimson)", () => {
    const targets: RecentTarget[] = [
      mkRecentTarget(1, "x", "completed", true, 0, "clean", 100),
      mkRecentTarget(2, "x", "failed", false, 5, "certain", 100),
    ]
    const { container } = render(<GlobeStatic targets={targets} />)
    const ellipses = container.querySelectorAll("ellipse")
    expect(ellipses.length).toBe(2)
    expect(ellipses[0].getAttribute("stroke")).toBe("#2DE08A")
    expect(ellipses[1].getAttribute("stroke")).toBe("#FF3B5C")
  })
})
