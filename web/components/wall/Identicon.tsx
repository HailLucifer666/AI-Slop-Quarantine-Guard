/**
 * Deterministic identicon — a 5×5 symmetric glyph derived from a string hash.
 * Abstract by design (no faces, no fabricated identity); just a stable visual
 * handle for a REAL ref/check so rows read like the reference's avatars.
 */
function hashStr(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return h >>> 0
}

export function Identicon({ seed, size = 26, className }: { seed: string; size?: number; className?: string }) {
  const h = hashStr(seed)
  const color = `hsl(${h % 360} 75% 62%)`
  const cells: [number, number][] = []
  for (let y = 0; y < 5; y++) {
    for (let x = 0; x < 3; x++) {
      if ((h >> (y * 3 + x)) & 1) {
        cells.push([x, y])
        if (x < 2) cells.push([4 - x, y])
      }
    }
  }
  return (
    <svg
      viewBox="0 0 5 5"
      width={size}
      height={size}
      className={className}
      style={{ borderRadius: 6, background: "rgba(255,255,255,0.05)", flexShrink: 0 }}
      aria-hidden
    >
      {cells.map(([x, y], i) => (
        <rect key={i} x={x} y={y} width={1.02} height={1.02} fill={color} />
      ))}
    </svg>
  )
}
