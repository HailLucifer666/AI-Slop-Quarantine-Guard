import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"

import { DataStreamFeed } from "@/components/wall/DataStreamFeed"
import { FIXTURE_AUDIT } from "./fixtures"

describe("DataStreamFeed — filter chips", () => {
  it("renders All / Failed / Block-eligible chips", () => {
    render(<DataStreamFeed feed={FIXTURE_AUDIT} />)
    expect(screen.getByRole("button", { name: "All" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Failed" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Block-eligible" })).toBeTruthy()
  })

  it("chips toggle aria-pressed", () => {
    render(<DataStreamFeed feed={FIXTURE_AUDIT} />)
    const all = screen.getByRole("button", { name: "All" })
    const failed = screen.getByRole("button", { name: "Failed" })
    expect(all.getAttribute("aria-pressed")).toBe("true")
    expect(failed.getAttribute("aria-pressed")).toBe("false")
    fireEvent.click(failed)
    expect(failed.getAttribute("aria-pressed")).toBe("true")
    expect(all.getAttribute("aria-pressed")).toBe("false")
  })

  it("the Failed filter shows only scan.failed events", () => {
    render(<DataStreamFeed feed={FIXTURE_AUDIT} />)
    fireEvent.click(screen.getByRole("button", { name: "Failed" }))
    const rows = screen.getAllByRole("listitem")
    expect(rows.length).toBe(1)
    expect(rows[0].textContent).toContain("scan failed")
    const all = rows.map((r) => r.textContent).join(" ")
    expect(all).not.toContain("shadow block")
    expect(all).not.toContain("settings updated")
  })

  it("the Block-eligible filter shows scan.completed events with block_eligible > 0", () => {
    render(<DataStreamFeed feed={FIXTURE_AUDIT} />)
    fireEvent.click(screen.getByRole("button", { name: "Block-eligible" }))
    const rows = screen.getAllByRole("listitem")
    expect(rows.length).toBe(2)
    rows.forEach((r) => expect(r.textContent).toContain("scan completed"))
  })

  it("the count line updates with the filtered count", () => {
    render(<DataStreamFeed feed={FIXTURE_AUDIT} />)
    expect(screen.getByText("7 events")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Failed" }))
    expect(screen.getByText("1 events")).toBeTruthy() // spec copy is "{n} events" (no singular form)
  })

  it("a filter with no matches renders the honest no-match copy", () => {
    render(<DataStreamFeed feed={[{ id: 1, action: "scan.failed", details: null, created_at: "2026-11-12T05:00:00.000Z" }]} />)
    fireEvent.click(screen.getByRole("button", { name: "Block-eligible" }))
    expect(screen.getByText(/No matching events/)).toBeTruthy()
  })

  it("unknown actions render the raw action string, known ones the plain name", () => {
    const feed = [
      { id: 1, action: "scan.created", details: null, created_at: "2026-11-12T05:00:00.000Z" },
      { id: 2, action: "weird.custom.action", details: null, created_at: "2026-11-12T05:01:00.000Z" },
    ]
    render(<DataStreamFeed feed={feed} />)
    expect(screen.getByText("scan created")).toBeTruthy()
    expect(screen.getByText("weird.custom.action")).toBeTruthy()
  })

  it("empty stream renders the honest awaiting copy", () => {
    render(<DataStreamFeed feed={[]} />)
    expect(screen.getByText(/Awaiting events/)).toBeTruthy()
  })
})
