import Link from "next/link"

import { shortRef } from "@/lib/format"
import type { RecentTarget } from "@/lib/useWallData"
import { Identicon } from "./Identicon"
import { SEV_COLOR } from "./tokens"

/**
 * Reference's "Users Reviewing & Commenting" — recent scan targets as an avatar
 * cluster with +N (findings) badges and ref labels beneath. Each links to its
 * scan detail (the wall is the navigator).
 */
export function AvatarTimeline({ targets }: { targets: RecentTarget[] }) {
  return (
    <div className="flex flex-col">
      {targets.length === 0 ? (
        <p className="mt-2 text-xs" style={{ color: "var(--wall-faint)" }}>
          No recent targets — scans appear here as they run.
        </p>
      ) : (
        <div className="relative mt-1 flex items-start justify-between gap-1 overflow-x-auto">
          <div className="pointer-events-none absolute inset-x-2 top-[18px] h-px" style={{ background: "var(--wall-line)" }} aria-hidden />
          {targets.map((t) => {
            const color = SEV_COLOR[t.sev]
            return (
              <Link
                key={t.id}
                href={`/analyses/${t.id}`}
                className="wall-click wall-focus relative flex min-w-0 flex-1 flex-col items-center gap-1.5"
                title={t.ref}
              >
                <span className="relative" style={{ filter: `drop-shadow(0 0 8px ${color}66)` }}>
                  <Identicon seed={t.ref} size={36} />
                  {t.findings > 0 && (
                    <span
                      className="wall-num absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px]"
                      style={{ background: color, color: "#04060c" }}
                    >
                      +{t.findings}
                    </span>
                  )}
                </span>
                <span className="max-w-full truncate text-[10px]" style={{ color: "var(--wall-faint)" }}>
                  {shortRef(t.ref)}
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
