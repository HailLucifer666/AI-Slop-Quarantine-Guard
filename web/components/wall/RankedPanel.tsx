"use client"

import { useState } from "react"
import { Star } from "lucide-react"

import { formatNumber, shortRef } from "@/lib/format"
import type { RankedCheck } from "@/lib/useWallData"
import { cn } from "@/lib/utils"
import type { Panel } from "./usePanel"
import { Identicon } from "./Identicon"
import { SEV_COLOR, SEV_ICON } from "./tokens"

/**
 * "Most Flagged" — demoted below Fix First in the left rail (spec §2a.3).
 * Top 5 rows, FULL check names (wrap to 2 lines — no ellipsis), severity icon
 * (14px, icon+color from tokens, paired with the name text) left of each check
 * name. Footer link opens the full checks catalog.
 */
export function RankedPanel({
  checks,
  files,
  onOpen,
}: {
  checks: RankedCheck[]
  files: { file_path: string; count: number }[]
  onOpen: (p: Panel) => void
}) {
  const [tab, setTab] = useState<"checks" | "files">("checks")

  const rows =
    tab === "checks"
      ? checks.slice(0, 5).map((c) => ({
          key: c.id,
          name: c.name,
          full: c.name,
          count: c.count,
          right: c.id,
          sevIcon: SEV_ICON[c.sev],
          sevColor: SEV_COLOR[c.sev],
          panel: "checks" as Panel,
        }))
      : files.slice(0, 5).map((f) => ({
          key: f.file_path,
          name: shortRef(f.file_path),
          full: f.file_path,
          count: f.count,
          right: "",
          sevIcon: null,
          sevColor: "var(--accent-cyan)",
          panel: "analyses" as Panel,
        }))

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="wall-label">Most Flagged</div>
      <div className="mt-2 flex items-center justify-between text-sm">
        <button
          onClick={() => setTab("checks")}
          className={cn("wall-focus rounded-sm transition-colors", tab !== "checks" && "opacity-50")}
          style={{ color: tab === "checks" ? "var(--accent-magenta)" : "var(--text-muted)" }}
          aria-pressed={tab === "checks"}
        >
          Top Checks
        </button>
        <button
          onClick={() => setTab("files")}
          className={cn("wall-focus rounded-sm transition-colors", tab !== "files" && "opacity-50")}
          style={{ color: "var(--text-muted)" }}
          aria-pressed={tab === "files"}
        >
          Top Files
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="wall-sub mt-4">
          No findings yet — ranked checks appear once issues are detected.
        </p>
      ) : (
        <ul className="wall-scroll mt-2 flex min-h-0 flex-1 flex-col overflow-y-auto pr-1">
          {rows.map((r, i) => (
            <li key={r.key}>
              <button
                onClick={() => onOpen(r.panel)}
                title={r.full}
                className="wall-click wall-focus flex min-h-[44px] w-full items-center gap-2.5 rounded-md py-1.5 text-left"
              >
                <span className="wall-num w-3 shrink-0 text-center text-xs" style={{ color: "var(--text-faint)" }}>
                  {i + 1}
                </span>
                <Identicon seed={r.key} size={22} />
                {r.sevIcon ? (
                  <r.sevIcon className="h-3.5 w-3.5 shrink-0" style={{ color: r.sevColor }} aria-hidden />
                ) : (
                  <Star className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--accent-cyan)" }} aria-hidden />
                )}
                <span className="min-w-0 flex-1 text-sm" style={{ color: "var(--text)" }}>
                  <span className="line-clamp-2">{r.name}</span>
                </span>
                <span className="wall-num shrink-0 text-xs" style={{ color: "var(--text-muted)" }}>
                  {formatNumber(r.count)}
                </span>
                {r.right && (
                  <span className="hidden w-16 shrink-0 text-right font-mono text-xs md:inline" style={{ color: "var(--text-faint)" }}>
                    {r.right}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        onClick={() => onOpen("checks")}
        className="wall-focus mt-2 inline-flex min-h-[44px] shrink-0 items-center gap-1 self-start rounded-md text-sm"
        style={{ color: "var(--accent-cyan)" }}
      >
        All checks →
      </button>
    </div>
  )
}
