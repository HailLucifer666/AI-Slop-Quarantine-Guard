"use client"

import Link from "next/link"
import { motion } from "framer-motion"
import { ShieldCheck } from "lucide-react"
import type { CSSProperties } from "react"

import { formatNumber, formatRelativeTime, shortRef } from "@/lib/format"
import type { FixFirstRow } from "@/lib/useWallData"
import { SEV_COLOR, SEV_ICON, SEV_LABEL } from "./tokens"
import { useReducedMotion } from "./useReducedMotion"

/**
 * Fix First (spec §3) — the prioritized queue answering "what do I fix first".
 * Rows are recent scans ranked by block-eligible findings (derived in
 * useWallData.derive()); each links to the full analysis. Honest empty states:
 * one for "no scans yet", one for "all scans came back clean".
 */

function chipColor(color: string): CSSProperties {
  return { "--chip-color": color } as CSSProperties
}

function Header() {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <div className="wall-label">Fix First</div>
      <div className="wall-sub">by block-eligible findings</div>
    </div>
  )
}

function Row({ row, rank, reduced }: { row: FixFirstRow; rank: number; reduced: boolean }) {
  const Icon = SEV_ICON[row.sev]
  const link = (
    <Link
      href={`/analyses/${row.scanId}`}
      title={row.ref}
      aria-label={`${row.ref} — ${formatNumber(row.blockEligible)} block-eligible, ${formatNumber(row.advisories)} advisory`}
      className="wall-focus flex min-h-[44px] w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-white/[0.04]"
    >
      <span className="wall-num w-4 shrink-0 text-right text-xs" style={{ color: "var(--text-faint)" }}>
        {rank}
      </span>
      <span className="wall-chip wall-chip-sm shrink-0" style={chipColor(SEV_COLOR[row.sev])}>
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {SEV_LABEL[row.sev]}
      </span>
      <span className="min-w-0 flex-1">
        {row.topChecks.length > 0 ? (
          <span className="line-clamp-2 text-sm" style={{ color: "var(--text)" }}>
            {row.topChecks.map((c) => `${c.name} ×${c.count}`).join(" · ")}
          </span>
        ) : (
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Rule breakdown unavailable for this scan
          </span>
        )}
        <span className="wall-mono mt-0.5 flex items-center gap-1" title={row.ref}>
          <span className="min-w-0 truncate" style={{ color: "var(--text-muted)" }}>
            {shortRef(row.ref)}
          </span>
          <span className="shrink-0" style={{ color: "var(--text-faint)" }}>·</span>
          <span className="shrink-0" style={{ color: "var(--text-faint)" }}>{formatRelativeTime(row.at)}</span>
        </span>
      </span>
      <span className="shrink-0 text-right">
        <span className="wall-num block text-xl" style={{ color: "var(--sev-certain)" }}>
          {formatNumber(row.blockEligible)}
        </span>
        <span className="block text-xs" style={{ color: "var(--text-muted)" }}>block-eligible</span>
        {row.advisories > 0 && (
          <span className="block text-xs" style={{ color: "var(--text-faint)" }}>
            · {formatNumber(row.advisories)} advisory
          </span>
        )}
      </span>
    </Link>
  )
  // Entrance: 40ms stagger, transform/opacity only (cap 8 — the list caps at 5).
  // Reduced motion renders final state directly (no motion wrapper).
  if (reduced) return <li>{link}</li>
  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(rank - 1, 8) * 0.04, ease: [0.22, 1, 0.36, 1] }}
    >
      {link}
    </motion.li>
  )
}

export function FixFirst({ rows, completed }: { rows: FixFirstRow[]; completed: number }) {
  const reduced = useReducedMotion()

  if (completed === 0) {
    return (
      <div>
        <Header />
        <div className="wall-empty">
          <ShieldCheck className="wall-empty-icon h-5 w-5" aria-hidden />
          <div className="wall-empty-title">Nothing to fix yet</div>
          <p className="wall-empty-body">
            Run your first scan — Fix First ranks scans by the findings that would block a merge.
          </p>
          <Link href="/scan" className="wall-empty-cta wall-focus rounded-sm">
            Open Scan
          </Link>
        </div>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div>
        <Header />
        <div className="wall-empty">
          <ShieldCheck className="wall-empty-icon h-5 w-5" style={{ color: "var(--sev-clean)" }} aria-hidden />
          <div className="wall-empty-title">All clear</div>
          <p className="wall-empty-body">
            No block-eligible findings in the last {completed} scans. Advisory findings still appear under Most Flagged.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <Header />
      <ul className="mt-1 flex flex-col">
        {rows.map((r, i) => (
          <Row key={r.scanId} row={r} rank={i + 1} reduced={reduced} />
        ))}
      </ul>
    </div>
  )
}
