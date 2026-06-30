"use client"

import { useState } from "react"
import { Star } from "lucide-react"

import { formatNumber, shortRef } from "@/lib/format"
import type { RankedCheck } from "@/lib/useWallData"
import { cn } from "@/lib/utils"
import type { Panel } from "./usePanel"
import { Identicon } from "./Identicon"
import { SEV_COLOR } from "./tokens"

/**
 * Reference's "Trending Developers" ranked list, hybridised: identicon · name ·
 * count cluster · right-aligned rule/repo, fading toward the bottom. Toggles
 * Top Checks / Top Files. Rows open the matching overlay (no page nav).
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
      ? checks.slice(0, 9).map((c) => ({ key: c.id, name: c.name, count: c.count, right: c.id, color: SEV_COLOR[c.sev], panel: "checks" as Panel }))
      : files.slice(0, 9).map((f) => ({ key: f.file_path, name: shortRef(f.file_path), count: f.count, right: "", color: "var(--wall-cyan)", panel: "analyses" as Panel }))

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="wall-label">Most Flagged</div>
      <div className="mt-2 flex items-center justify-between text-[11px]">
        <button
          onClick={() => setTab("checks")}
          className={cn("wall-focus transition-colors", tab !== "checks" && "opacity-50")}
          style={{ color: tab === "checks" ? "var(--wall-magenta)" : "var(--wall-muted)" }}
          aria-pressed={tab === "checks"}
        >
          Top Checks
        </button>
        <button
          onClick={() => setTab("files")}
          className={cn("wall-focus transition-colors", tab !== "files" && "opacity-50")}
          style={{ color: "var(--wall-muted)" }}
          aria-pressed={tab === "files"}
        >
          Top Files
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="mt-4 text-xs" style={{ color: "var(--wall-faint)" }}>
          No findings yet — ranked items appear once issues are detected.
        </p>
      ) : (
        <ul
          className="mt-2 flex min-h-0 flex-col"
          style={{ maskImage: "linear-gradient(to bottom,#000 72%,transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom,#000 72%,transparent 100%)" }}
        >
          {rows.map((r, i) => (
            <li key={r.key}>
              <button onClick={() => onOpen(r.panel)} className="wall-click wall-focus flex w-full items-center gap-3 rounded-md py-1.5 text-left">
                <span className="wall-num w-3 text-center text-[11px]" style={{ color: "var(--wall-faint)" }}>
                  {i + 1}
                </span>
                <Identicon seed={r.key} size={26} />
                <span className="min-w-0 flex-1 truncate text-sm" style={{ color: "var(--wall-text)" }} title={r.name}>
                  {r.name}
                </span>
                <span className="flex items-center gap-1 text-[11px]" style={{ color: "var(--wall-muted)" }}>
                  <Star className="h-3 w-3" style={{ color: r.color }} aria-hidden />
                  <span className="wall-num">{formatNumber(r.count)}</span>
                </span>
                {r.right && (
                  <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] md:inline" style={{ color: "var(--wall-faint)" }}>
                    {r.right}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
