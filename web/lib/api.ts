/**
 * Typed wrappers over the FastAPI scan endpoints. REAL DATA ONLY — no mock/fixture
 * branch. Set NEXT_PUBLIC_API_URL to point at the API (defaults to :8000). When the
 * API is down, calls reject and the UI shows honest error / empty states.
 */
import type {
  AppSettings,
  AuditEntry,
  Explanation,
  Finding,
  ScanDetail,
  ScanListPage,
  ScanSummary,
  ScansSummary,
} from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
/** Reachable base URL for callers outside this module (e.g. the shell health poll). */
export const API_BASE = BASE

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export async function startUrlScan(url: string): Promise<{ scan_id: number }> {
  return asJson(
    await fetch(`${BASE}/api/scans`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "url", url }),
    }),
  )
}

export async function startLocalScan(path: string): Promise<{ scan_id: number }> {
  return asJson(
    await fetch(`${BASE}/api/scans`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "local", path }),
    }),
  )
}

export async function startZipScan(file: File): Promise<{ scan_id: number }> {
  const form = new FormData()
  form.append("file", file)
  return asJson(await fetch(`${BASE}/api/scans`, { method: "POST", body: form }))
}

export async function getScan(id: number | string): Promise<ScanDetail> {
  return asJson(await fetch(`${BASE}/api/scans/${id}`, { cache: "no-store" }))
}

export async function listScans(): Promise<ScanSummary[]> {
  const data = await asJson<{ scans: ScanSummary[] }>(
    await fetch(`${BASE}/api/scans`, { cache: "no-store" }),
  )
  return data.scans
}

/** Paginated scan history (up to 100/page) — for a full archive view beyond the
 * 50-row default `listScans()` returns. */
export async function listScansPage(opts: { limit?: number; offset?: number } = {}): Promise<ScanListPage> {
  const params = new URLSearchParams()
  if (opts.limit != null) params.set("limit", String(opts.limit))
  if (opts.offset != null) params.set("offset", String(opts.offset))
  const qs = params.toString()
  return asJson(await fetch(`${BASE}/api/scans${qs ? `?${qs}` : ""}`, { cache: "no-store" }))
}

/** Cross-scan rollup (clean-pass-rate, totals, by-rule, top-files) computed
 * server-side — cheaper than re-deriving it client-side from a capped list. */
export async function getScansSummary(range: string = "30d"): Promise<ScansSummary> {
  return asJson(
    await fetch(`${BASE}/api/scans/summary?range=${encodeURIComponent(range)}`, { cache: "no-store" }),
  )
}

/** Live scan progress via Server-Sent Events. Returns an unsubscribe function.
 * `onEvent` fires on every status/progress change; the connection closes itself
 * once the scan reaches a terminal status or the server-side lifetime cap hits —
 * callers should keep their own poll as a fallback for that case. */
export function streamScanEvents(
  id: number | string,
  onEvent: (payload: { status: string; progress: unknown }) => void,
  onDone?: () => void,
): () => void {
  const source = new EventSource(`${BASE}/api/scans/${id}/events`)
  source.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data))
    } catch {
      /* malformed frame — ignore, next one will likely be fine */
    }
  }
  source.addEventListener("timeout", () => {
    source.close()
    onDone?.()
  })
  source.addEventListener("error", () => {
    source.close()
    onDone?.()
  })
  return () => source.close()
}

/** The Crew (Phase 7) — advisory plain-English explanation of one finding. */
export async function explainFinding(finding: Finding): Promise<Explanation> {
  return asJson(
    await fetch(`${BASE}/api/crew/explain`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(finding),
    }),
  )
}

/** Audit trail — the lifecycle record of Guard actions, newest first. */
export async function listAudit(): Promise<AuditEntry[]> {
  const data = await asJson<{ audit: AuditEntry[] }>(
    await fetch(`${BASE}/api/audit`, { cache: "no-store" }),
  )
  return data.audit
}

/** Global gate settings. */
export async function getSettings(): Promise<AppSettings> {
  return asJson(await fetch(`${BASE}/api/settings`, { cache: "no-store" }))
}

export async function updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  return asJson(
    await fetch(`${BASE}/api/settings`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  )
}
