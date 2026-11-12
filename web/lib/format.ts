/** Small display formatters (tabular-friendly). */

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—"
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  return `${m}m ${Math.round(s % 60)}s`
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—"
  return n.toLocaleString("en-US")
}

export function formatRelativeTime(iso: string | number | null | undefined): string {
  if (iso == null || iso === "") return "—"
  const then = typeof iso === "number" ? iso : new Date(iso).getTime()
  if (Number.isNaN(then)) return "—"
  const diff = Date.now() - then
  const sec = Math.round(diff / 1000)
  if (sec < 60) return "just now"
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  return `${day}d ago`
}

/** A scan's `ref` can be a long URL/path — show the meaningful tail. */
export function shortRef(ref: string): string {
  const cleaned = ref.replace(/\/+$/, "")
  const parts = cleaned.split(/[\\/]/)
  if (cleaned.includes("github.com") || cleaned.includes("gitlab.com") || cleaned.includes("bitbucket.org")) {
    return parts.slice(-2).join("/")
  }
  return parts[parts.length - 1] || ref
}
