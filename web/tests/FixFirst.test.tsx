import React from "react"
import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"

// jsdom has no Next App Router; outside it <Link> throws "invariant expected
// app router to be mounted". Mock the framework boundary only — it renders the
// same <a href> the real Link would, so href/aria-label assertions stay honest.
vi.mock("next/link", () => ({
  default: (props: { href: string; children?: React.ReactNode; [k: string]: unknown }) => {
    const { href, children, ...rest } = props
    return React.createElement("a", { href, ...rest }, children)
  },
}))

import { FixFirst } from "@/components/wall/FixFirst"
import type { FixFirstRow } from "@/lib/useWallData"

const ROWS: FixFirstRow[] = [
  {
    scanId: 2,
    ref: "https://github.com/acarg/secret-leaker",
    blockEligible: 3,
    advisories: 0,
    topChecks: [
      { id: "SQG002", name: "Leaked secret", count: 6 },
      { id: "SQG001", name: "Hallucinated package", count: 2 },
    ],
    sev: "certain",
    at: new Date("2026-11-12T05:00:00.000Z").getTime(),
  },
  {
    scanId: 1,
    ref: "https://github.com/acarg/sloppy-backend",
    blockEligible: 3,
    advisories: 1,
    topChecks: [
      { id: "SQG001", name: "Hallucinated package", count: 5 },
      { id: "SQG004", name: "Vulnerable dependency", count: 3 },
    ],
    sev: "certain",
    at: new Date("2026-11-12T04:00:00.000Z").getTime(),
  },
]

it("renders rows from fixture data in ranked order", () => {
  render(<FixFirst rows={ROWS} completed={2} />)
  const links = screen.getAllByRole("link")
  expect(links.length).toBe(2)
  // Rank 1 = B (newest of the block=3 ties), rank 2 = A.
  expect(links[0].getAttribute("aria-label")).toContain("secret-leaker")
  expect(links[1].getAttribute("aria-label")).toContain("sloppy-backend")
  // Top check names render with counts, joined by " · ".
  expect(links[0].textContent).toContain("Leaked secret ×6")
  expect(links[0].textContent).toContain("Hallucinated package ×2")
  // The advisory line appears only when advisories > 0.
  expect(links[1].textContent).toContain("1 advisory")
  expect(links[0].textContent).not.toContain("advisory")
})

it("links point to /analyses/{id}", () => {
  render(<FixFirst rows={ROWS} completed={2} />)
  const links = screen.getAllByRole("link")
  expect(links[0].getAttribute("href")).toBe("/analyses/2")
  expect(links[1].getAttribute("href")).toBe("/analyses/1")
})

it("empty state when there are no completed scans", () => {
  render(<FixFirst rows={[]} completed={0} />)
  expect(screen.getByText("Nothing to fix yet")).toBeTruthy()
  expect(screen.getByText(/Run your first scan/)).toBeTruthy()
  const cta = screen.getByRole("link", { name: /open scan/i })
  expect(cta.getAttribute("href")).toBe("/scan")
})

it("all-clear empty state when completed scans exist but none block", () => {
  render(<FixFirst rows={[]} completed={4} />)
  expect(screen.getByText("All clear")).toBeTruthy()
  expect(screen.getByText(/No block-eligible findings in the last 4 scans/)).toBeTruthy()
  expect(screen.queryByRole("link", { name: /open scan/i })).toBeNull()
})

it("pre-analytics row renders the honest rule-breakdown fallback", () => {
  const partial: FixFirstRow[] = [
    { scanId: 9, ref: "https://github.com/acarg/no-analytics", blockEligible: 1, advisories: 0, topChecks: [], sev: "medium", at: new Date("2026-11-12T03:00:00.000Z").getTime() },
  ]
  render(<FixFirst rows={partial} completed={1} />)
  expect(screen.getByText("Rule breakdown unavailable for this scan")).toBeTruthy()
})
