import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"

import { SeverityBadge } from "@/components/findings/SeverityBadge"

// getByText returns the .wall-chip span itself — the label is its direct text
// node. Assertions use plain DOM reads (getAttribute/textContent/querySelector):
// this vitest install has no @testing-library/jest-dom, so jest-dom matchers
// (toBeInTheDocument, toHaveAttribute...) do not exist.
describe("SeverityBadge — icon + text + color, never color-only", () => {
  it.each([
    ["CERTAIN", "Certain"],
    ["HIGH", "High"],
    ["MEDIUM", "Medium"],
  ] as const)("renders the %s badge with an icon, the tier word and --chip-color", (confidence, word) => {
    render(<SeverityBadge confidence={confidence} />)
    const chip = screen.getByText(word)
    // The accessible name carries the word — severity is never color-only.
    expect(chip.textContent).toContain(word)
    // Icon present next to the text.
    expect(chip.querySelector("svg")).toBeTruthy()
    // Color comes from the warm-ramp token, set per instance.
    expect(chip.getAttribute("style")).toContain("--chip-color")
  })
})
