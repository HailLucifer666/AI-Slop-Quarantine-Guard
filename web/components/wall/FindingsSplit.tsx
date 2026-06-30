import { formatNumber } from "@/lib/format"

/**
 * Findings summary — one huge figure for total findings caught, then an honest
 * breakdown: how many are block-eligible (provable, would-block) vs advisory
 * (everything else). Keeps a non-technical reader from reading "517" as 517
 * blocking errors when almost all are advisory.
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
      <div className="wall-label">
        Findings <span style={{ color: "var(--wall-green)" }}>Cleared</span>/<span style={{ color: "var(--wall-act-failed)" }}>Caught</span>
      </div>
      <div className="wall-figure wall-grad-cool mt-2 text-[clamp(2.1rem,4vw,3.6rem)]">{formatNumber(findings)}</div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span style={{ color: "var(--wall-act-failed)" }}>
          <span className="wall-num">{formatNumber(blockEligible)}</span> block-eligible
        </span>
        <span style={{ color: "var(--wall-muted)" }}>
          <span className="wall-num">{formatNumber(advisory)}</span> advisory
        </span>
        <span className="ml-auto" style={{ color: "var(--wall-green)" }}>
          <span className="wall-num">{formatNumber(cleanPasses)}</span> clean
        </span>
      </div>
    </div>
  )
}
