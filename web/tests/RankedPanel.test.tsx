import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"

import { RankedPanel } from "@/components/wall/RankedPanel"
import { FIXTURE_RANKED_CHECKS } from "./fixtures"

describe("RankedPanel — Most Flagged", () => {
  it("renders FULL check names on the data (line-clamp is CSS-only, data intact)", () => {
    render(<RankedPanel checks={FIXTURE_RANKED_CHECKS} files={[]} onOpen={() => {}} />)
    // Exact-match getByText proves the whole name is present, not a truncated tail.
    const name = screen.getByText("Leaked secret")
    expect(name.textContent).toBe("Leaked secret")
    expect(screen.getByText("Hallucinated package")).toBeTruthy()
    expect(screen.getByText("Vulnerable dependency")).toBeTruthy()
    expect(screen.getByText("Possible typosquat")).toBeTruthy()
    // The full name is also the accessible name via the row's title.
    expect(name.closest("button")!.getAttribute("title")).toBe("Leaked secret")
  })

  it("a lucide severity icon renders per check row", () => {
    render(<RankedPanel checks={FIXTURE_RANKED_CHECKS} files={[]} onOpen={() => {}} />)
    const row = screen.getByText("Leaked secret").closest("button")!
    // Identicon is a plain <svg>; the severity icon carries the lucide class.
    expect(row.querySelector("svg.lucide")).toBeTruthy()
  })

  it("Top Checks is pressed by default, Top Files is not", () => {
    render(<RankedPanel checks={FIXTURE_RANKED_CHECKS} files={[]} onOpen={() => {}} />)
    expect(screen.getByRole("button", { name: "Top Checks" }).getAttribute("aria-pressed")).toBe("true")
    expect(screen.getByRole("button", { name: "Top Files" }).getAttribute("aria-pressed")).toBe("false")
  })

  it("switches to Top Files on tab activation", () => {
    render(
      <RankedPanel
        checks={FIXTURE_RANKED_CHECKS}
        files={[{ file_path: "backend/ai/gen.py", count: 5 }]}
        onOpen={() => {}}
      />,
    )
    const filesTab = screen.getByRole("button", { name: "Top Files" })
    filesTab.focus()
    // jsdom does not run native activation behavior; in a real browser Enter or
    // Space on this focused native <button> produces exactly this click event.
    fireEvent.click(filesTab)
    expect(filesTab.getAttribute("aria-pressed")).toBe("true")
    // Short name on the data, full path in the title/accessible name.
    expect(screen.getByText("gen.py")).toBeTruthy()
    expect(screen.getByText("gen.py").closest("button")!.getAttribute("title")).toBe("backend/ai/gen.py")
  })

  it("renders the honest empty copy when there are no checks", () => {
    render(<RankedPanel checks={[]} files={[]} onOpen={() => {}} />)
    expect(screen.getByText(/No findings yet/)).toBeTruthy()
  })
})
