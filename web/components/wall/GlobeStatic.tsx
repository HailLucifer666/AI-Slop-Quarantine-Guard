"use client"

import { shortRef } from "@/lib/format"
import type { RecentTarget } from "@/lib/useWallData"
import { SEV_HEX } from "./tokens"

/**
 * Static SVG fallback for the globe — used under prefers-reduced-motion or when
 * WebGL is unavailable (spec §6.2). Honors the SAME color/thickness/label
 * contract as the 3D data rings (GlobeCore) — a fallback, not a dumbed-down
 * cousin. Each orbit is a real <a> link, so the frame stays keyboard operable
 * without JS event handlers.
 */

/** Ring radius 1.06–1.20 in globe units → px on the 400×400 viewBox. */
const SCALE = 140

function ringColor(t: RecentTarget): string {
  if (t.status === "completed") return t.clean ? SEV_HEX.clean : SEV_HEX[t.sev]
  if (t.status === "failed") return SEV_HEX.certain // act-failed shares the crimson value
  return "#16e0e0" // queued | running — accent-cyan token value (live state)
}

export function GlobeStatic({ targets }: { targets: RecentTarget[] }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-1">
      <svg viewBox="0 0 400 400" className="h-full w-full">
        <defs>
          <radialGradient id="wall-earth-static">
            <stop offset="0%" stopColor="#0a1126" />
            <stop offset="100%" stopColor="#02030a" />
          </radialGradient>
        </defs>
        {/* Decorative brand backdrop — not data. */}
        <circle cx="200" cy="200" r="140" fill="url(#wall-earth-static)" aria-hidden />
        {targets.map((t, i) => {
          const r = (1.06 + i * 0.02) * SCALE // newest innermost, matches the 3D radii
          const ry = r * Math.cos(0.35 + i * 0.09) // tilt → ellipse squash
          const rot = ((i * 0.45 + 0.12 * i - 0.3) * 180) / Math.PI // Euler → 2D rotation
          const stroke = 2 + 3 * Math.min(1, Math.max(0, t.filesScanned) / 5000) // 2–5px
          return (
            <a
              key={t.id}
              href={`/analyses/${t.id}`}
              aria-label={`Scan ${shortRef(t.ref)} — ${t.status}, ${t.filesScanned} files, ${t.findings} findings`}
            >
              <ellipse
                cx="200"
                cy="200"
                rx={r}
                ry={Math.max(8, ry)}
                transform={`rotate(${rot} 200 200)`}
                fill="none"
                stroke={ringColor(t)}
                strokeOpacity={0.45}
                strokeWidth={stroke}
              />
            </a>
          )
        })}
      </svg>
      <p className="wall-ring-legend px-3 text-center">
        {targets.length === 0
          ? "Orbits appear after your first scan."
          : `Orbits = last ${targets.length} scans · thickness = files scanned · colour = status`}
      </p>
    </div>
  )
}
