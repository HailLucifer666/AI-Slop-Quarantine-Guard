import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"

import { StatusBadge } from "@/components/findings/StatusBadge"
import type { ScanStatus } from "@/lib/types"

// Only real ScanStatus values — "clean"/"findings" are internal map keys, not
// props. Plain DOM reads (see SeverityBadge note on jest-dom matchers).
describe("StatusBadge — icon + text + color, never color-only", () => {
  it.each([
    ["queued", undefined, "Queued"],
    ["running", undefined, "Scanning"],
    ["failed", undefined, "Failed"],
    ["completed", true, "All clear"],
    ["completed", false, "Findings"],
  ] as const)("renders %s (clean=%s) as the '%s' chip", (status, clean, word) => {
    render(<StatusBadge status={status as ScanStatus} clean={clean} />)
    const chip = screen.getByText(word)
    expect(chip.textContent).toContain(word)
    expect(chip.querySelector("svg")).toBeTruthy()
    expect(chip.getAttribute("style")).toContain("--chip-color")
  })
})
