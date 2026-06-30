/** Clean-pass-rate radial gauge — pure SVG, aurora-gradient arc. Value 0–100. */
export function RadialGauge({ value, label }: { value: number; label: string }) {
  const r = 52
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, value))
  const offset = c - (pct / 100) * c

  return (
    <div className="flex flex-col items-center justify-center" role="img" aria-label={`${label}: ${pct}%`}>
      <svg width="140" height="140" viewBox="0 0 140 140">
        <defs>
          <linearGradient id="gauge-aurora" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#4A5BFF" />
            <stop offset="52%" stopColor="#16C8D4" />
            <stop offset="100%" stopColor="#2DE08A" />
          </linearGradient>
        </defs>
        <circle cx="70" cy="70" r={r} fill="none" stroke="rgba(120,140,255,0.12)" strokeWidth="10" />
        <circle
          cx="70"
          cy="70"
          r={r}
          fill="none"
          stroke="url(#gauge-aurora)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform="rotate(-90 70 70)"
        />
        <text x="70" y="66" textAnchor="middle" className="fill-text font-display" fontSize="28" fontWeight="700">
          {pct}%
        </text>
        <text x="70" y="86" textAnchor="middle" className="fill-text-faint" fontSize="10">
          clean
        </text>
      </svg>
      <span className="mt-1 text-xs uppercase tracking-wide text-text-faint">{label}</span>
    </div>
  )
}
