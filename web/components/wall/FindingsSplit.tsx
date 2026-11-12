import { formatNumber } from "@/lib/format"

/**
 * Bottom-strip tile 1 (spec §5) — "Findings Caught": one plain figure for total
 * findings, then the honest breakdown: block-eligible (provable, would-block)
 * vs advisory (everything else) vs clean passes. No brand gradient on a findings
 * figure — the inline counts carry the severity colors. The wrapping tile in
 * page.tsx is the single button → /analyses (nested buttons would be invalid
 * HTML, and every count shares the tile's destination).
 */
export function FindingsSplit({
  cleanPasses,
  findings,
  blockEligible,
}: {
  cleanPasses: number
  findings: number
  blockEligible: number
}) {
  const advisory = Math.max(0, findings - blockEligible)
  return (
    <div className="flex flex-col">
      <div className="wall-label">Findings Caught</div>
      <div className="wall-figure-tile mt-2" style={{ color: "var(--text)" }}>
        {formatNumber(findings)}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span style={{ color: "var(--sev-certain)" }}>
          <span className="wall-num">{formatNumber(blockEligible)}</span> block-eligible
        </span>
        <span style={{ color: "var(--text-muted)" }}>
          <span className="wall-num">{formatNumber(advisory)}</span> advisory
        </span>
        <span className="ml-auto" style={{ color: "var(--sev-clean)" }}>
          <span className="wall-num">{formatNumber(cleanPasses)}</span> clean
        </span>
      </div>
    </div>
  )
}
