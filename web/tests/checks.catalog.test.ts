import { describe, it, expect } from "vitest"

import { CHECKS, RULE_IDS, checkName } from "@/lib/checks"
import type { CheckMeta } from "@/lib/checks"

/**
 * Integrity test for the SQG check catalog. The catalog is the single source the
 * UI iterates; every rule the backend can emit must appear here, and nothing
 * unimplemented may leak into the display.
 */

describe("web/lib/checks.ts — catalog integrity", () => {
  it("contains every implemented rule id SQG001-SQG007 plus SQG009", () => {
    const expected = ["SQG001", "SQG002", "SQG003", "SQG004", "SQG005", "SQG006", "SQG007", "SQG009"]
    const actual = Object.keys(CHECKS).sort()
    expect(actual).toEqual(expected)
  })

  it("RULE_IDS mirrors CHECKS keys", () => {
    expect(RULE_IDS.sort()).toEqual(Object.keys(CHECKS).sort())
  })

  it("every registered check has id, name, blurb, blockEligible and severity", () => {
    Object.values(CHECKS).forEach((check) => {
      expect(check).toHaveProperty("id")
      expect(check).toHaveProperty("name")
      expect(check).toHaveProperty("blurb")
      expect(check).toHaveProperty("blockEligible")
      expect(check).toHaveProperty("severity")
      expect(typeof check.name).toBe("string")
      expect(check.name.length).toBeGreaterThan(0)
      expect(check.id).toMatch(/^SQG\d{3}$/)
      expect(typeof check.blockEligible).toBe("boolean")
      expect(["certain", "high", "medium", "clean"]).toContain(check.severity)
    })
  })

  it("severity matches the warm-ramp mapping in design/dashboard-overhaul.md §1a/§3.2: certain -> SQG001/002, high -> 004/005/006, medium -> 003/007/009", () => {
    expect(CHECKS.SQG001.severity).toBe("certain")
    expect(CHECKS.SQG002.severity).toBe("certain")
    expect(CHECKS.SQG003.severity).toBe("medium")
    expect(CHECKS.SQG004.severity).toBe("high")
    expect(CHECKS.SQG005.severity).toBe("high")
    expect(CHECKS.SQG006.severity).toBe("high")
    expect(CHECKS.SQG007.severity).toBe("medium")
    expect(CHECKS.SQG009.severity).toBe("medium")
  })

  it("SQG008 is absent by design", () => {
    expect(CHECKS).not.toHaveProperty("SQG008")
    expect(RULE_IDS).not.toContain("SQG008")
    expect(checkName("SQG008")).toBe("SQG008") // no lookup => id fallback
  })

  it("checkName resolves registered ids to human names", () => {
    expect(checkName("SQG001")).toBe("Hallucinated package")
    expect(checkName("SQG006")).toBe("Security issue")
  })

  it("blockEligible exactly on the G2 pair (SQG001/SQG002)", () => {
    expect(CHECKS.SQG001.blockEligible).toBe(true)
    expect(CHECKS.SQG002.blockEligible).toBe(true)
    Object.entries(CHECKS).forEach(([id, check]) => {
      if (!["SQG001", "SQG002"].includes(id)) {
        expect(check.blockEligible).toBe(false)
      }
    })
  })
})
