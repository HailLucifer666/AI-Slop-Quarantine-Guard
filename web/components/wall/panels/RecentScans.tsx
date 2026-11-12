"use client"

import { formatNumber, shortRef } from "@/lib/format"
import type { RecentTarget } from "@/lib/useWallData"
import { Identicon } from "@/components/wall/Identicon"
import { SEV_COLOR } from "@/components/wall/tokens"

/**
 * Recent Scans (spec §6.4) — the globe's HTML twin: the keyboard/screen-reader
 * reachable list of the same recent scans the orbit rings render. Rows ≥44px,
 * badge text 12px, title + aria-label carry the full ref.
 */
export function RecentScans({ targets, onOpen }: { targets: RecentTarget[]; onOpen: (id: number) => void }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="wall-label">Recent Scans</div>
      {targets.length === 0 ? (
        <p className="wall-sub mt-3">
          No scans yet — start one from the Scan tab.
        </p>
      ) : (
        <ul
          className="wall-scroll mt-2 flex min-h-0 flex-1 flex-col overflow-y-auto pr-1"
          style={{ maskImage: "linear-gradient(to bottom,#000 95%,transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom,#000 95%,transparent 100%)" }}
        >
          {targets.map((t) => {
            const color = SEV_COLOR[t.sev]
            return (
              <li key={t.id}>
                <button
                  onClick={() => onOpen(t.id)}
                  title={t.ref}
                  aria-label={t.ref}
                  className="wall-click wall-focus flex min-h-[44px] w-full items-center gap-2.5 rounded-md py-2 text-left"
                >
                  <Identicon seed={t.ref} size={22} />
                  <span className="min-w-0 flex-1 truncate text-sm" style={{ color: "var(--text)" }}>
                    {shortRef(t.ref)}
                  </span>
                  <span
                    className="wall-num shrink-0 rounded-sm px-1.5 py-0.5 text-xs"
                    style={{ color: t.findings > 0 ? "var(--on-accent)" : "var(--text-muted)", background: t.findings > 0 ? color : "var(--line)" }}
                  >
                    {t.findings > 0 ? formatNumber(t.findings) : t.clean ? "clean" : t.status === "completed" ? "partial" : t.status}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
