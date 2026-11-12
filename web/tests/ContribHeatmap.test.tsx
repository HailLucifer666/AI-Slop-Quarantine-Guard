import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"

import { ContribHeatmap } from "@/components/wall/ContribHeatmap"
import type { HeatCell } from "@/lib/useWallData"
import { mkHeatCell } from "./fixtures"

it("renders real date axis labels (first / middle / last cell)", () => {
  const cells: HeatCell[] = [
    mkHeatCell("2026-10-01", 1),
    mkHeatCell("2026-10-15", 2),
    mkHeatCell("2026-11-12", 3),
  ]
  render(<ContribHeatmap cells={cells} scanned={6} />)
  const labels = screen.getAllByText(/aug|oct|nov/i)
  expect(labels.length).toBeGreaterThan(0)
})

it("renders the 'N scans so far' caption", () => {
  const cells: HeatCell[] = Array.from({ length: 91 }, (_, i) =>
    mkHeatCell(`2026-0${(i % 9) + 1}-${String((i % 28) + 1).padStart(2, "0")}`, i % 4),
  )
  render(<ContribHeatmap cells={cells} scanned={127} />)
  expect(screen.getByText("127 scans so far")).toBeTruthy()
})

it("zero-scan empty copy renders with caption", () => {
  render(<ContribHeatmap cells={[]} scanned={0} />)
  expect(screen.getByText(/no scans in the last 13 weeks yet/i)).toBeTruthy()
  expect(screen.getByText("0 scans so far")).toBeTruthy()
})

it("sr-only summary names the busiest day", () => {
  const cells: HeatCell[] = [mkHeatCell("2026-10-20", 5), mkHeatCell("2026-10-21", 1)]
  render(<ContribHeatmap cells={cells} scanned={6} />)
  expect(screen.getByText(/6 scans across the last 13 weeks/)).toBeTruthy()
})
