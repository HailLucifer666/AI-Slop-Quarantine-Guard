"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import { ChevronRight, Loader2, ScanLine, Search } from "lucide-react"

import { listScans } from "@/lib/api"
import { formatNumber, formatRelativeTime, shortRef } from "@/lib/format"
import type { ScanSummary } from "@/lib/types"
import { Identicon } from "@/components/wall/Identicon"

const POLL_MS = 12000
const TICK_MS = 30000

type StatusFilter = "all" | "clean" | "findings" | "failed" | "running"
const FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "clean", label: "Clean" },
  { id: "findings", label: "Findings" },
  { id: "failed", label: "Failed" },
  { id: "running", label: "Running" },
]

const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10)
const findingsOf = (s: ScanSummary) => s.analytics?.total_findings ?? 0
const isRunning = (s: ScanSummary) => s.status === "queued" || s.status === "running"

function dayLabel(key: string): string {
  if (key === isoDay(Date.now())) return "Today"
  if (key === isoDay(Date.now() - 86_400_000)) return "Yesterday"
  return new Date(key + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

function sevColor(s: ScanSummary): string {
  const c = s.analytics?.by_confidence
  if (!c) return "var(--wall-faint)"
  if ((c.CERTAIN ?? 0) > 0) return "var(--wall-sev-certain)"
  if ((c.HIGH ?? 0) > 0) return "var(--wall-sev-high)"
  if ((c.MEDIUM ?? 0) > 0) return "var(--wall-sev-medium)"
  return "var(--wall-sev-clean)"
}

function matchesStatus(s: ScanSummary, f: StatusFilter): boolean {
  switch (f) {
    case "clean":
      return s.status === "completed" && findingsOf(s) === 0
    case "findings":
      return s.status === "completed" && findingsOf(s) > 0
    case "failed":
      return s.status === "failed"
    case "running":
      return isRunning(s)
    default:
      return true
  }
}

/** Tiny stacked severity bar (certain/high/medium) from real by_confidence counts. */
function SeverityMicrobar({ s }: { s: ScanSummary }) {
  const c = s.analytics?.by_confidence
  const certain = c?.CERTAIN ?? 0
  const high = c?.HIGH ?? 0
  const medium = c?.MEDIUM ?? 0
  if (certain + high + medium === 0) return null
  const seg = (n: number, color: string) =>
    n > 0 ? <span style={{ flex: n, background: color }} aria-hidden /> : null
  return (
    <div className="hidden h-1.5 w-16 shrink-0 overflow-hidden rounded-full md:flex" style={{ background: "var(--wall-line)" }}>
      {seg(certain, "var(--wall-sev-certain)")}
      {seg(high, "var(--wall-sev-high)")}
      {seg(medium, "var(--wall-sev-medium)")}
    </div>
  )
}

/** Analyses explorer — live (polled), animated, grouped by day, searchable. */
export function AnalysesExplorer({ onOpen }: { onOpen: (id: number) => void }) {
  const [scans, setScans] = useState<ScanSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState<StatusFilter>("all")
  const [, setTick] = useState(0)
  const reduce = useReducedMotion()

  // Live poll — pause when the tab is hidden; keep the loop alive.
  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | null = null
    async function tick() {
      if (!alive) return
      if (typeof document === "undefined" || !document.hidden) {
        try {
          const s = await listScans()
          if (alive) {
            setScans(s)
            setError(null)
          }
        } catch (e) {
          if (alive) setError(e instanceof Error ? e.message : "Failed to load")
        }
      }
      timer = setTimeout(tick, POLL_MS)
    }
    tick()
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
  }, [])

  // Re-render every 30s so relative timestamps advance.
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), TICK_MS)
    return () => clearInterval(t)
  }, [])

  const stats = useMemo(() => {
    const list = scans ?? []
    const completed = list.filter((s) => s.status === "completed")
    const clean = completed.filter((s) => findingsOf(s) === 0).length
    const findings = completed.reduce((a, s) => a + findingsOf(s), 0)
    return {
      total: list.length,
      cleanRate: completed.length ? Math.round((clean / completed.length) * 100) : 100,
      findings,
      running: list.filter(isRunning).length,
    }
  }, [scans])

  const groups = useMemo(() => {
    if (!scans) return [] as [string, ScanSummary[]][]
    const q = query.trim().toLowerCase()
    const filtered = scans
      .filter((s) => s.created_at)
      .filter((s) => matchesStatus(s, status))
      .filter((s) => !q || s.ref.toLowerCase().includes(q))
      .sort((a, b) => (a.created_at! < b.created_at! ? 1 : -1))
    const map = new Map<string, ScanSummary[]>()
    for (const s of filtered) {
      const key = isoDay(new Date(s.created_at!).getTime())
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(s)
    }
    return [...map.entries()]
  }, [scans, query, status])

  const shown = groups.reduce((a, [, rows]) => a + rows.length, 0)

  if (error && !scans)
    return <p className="text-sm" style={{ color: "var(--wall-act-failed)" }}>{error} — is the API running on :8000?</p>
  if (!scans)
    return <p className="flex items-center gap-2 text-sm" style={{ color: "var(--wall-muted)" }}><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
  if (scans.length === 0)
    return (
      <div className="flex flex-col items-start gap-4 rounded-xl p-8" style={{ border: "1px solid var(--wall-line)" }}>
        <p className="text-sm" style={{ color: "var(--wall-muted)" }}>No scans yet — run your first one to populate Analyses.</p>
        <Link href="/scan" className="wall-cta inline-flex w-auto items-center gap-2">
          <ScanLine className="h-4 w-4" aria-hidden /> Start a scan
        </Link>
      </div>
    )

  let flatIndex = 0

  return (
    <div className="flex flex-col gap-4">
      {/* Summary header — derived from real rows. */}
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm" style={{ color: "var(--wall-muted)" }}>
        <Stat label="scans" value={formatNumber(stats.total)} />
        <Stat label="clean" value={`${stats.cleanRate}%`} color="var(--wall-green)" />
        <Stat label="findings" value={formatNumber(stats.findings)} />
        {stats.running > 0 && <Stat label="running" value={formatNumber(stats.running)} color="var(--wall-cyan)" pulse />}
      </div>

      {/* Filter + search. */}
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 py-1" style={{ background: "var(--wall-bg)" }}>
        <div className="relative min-w-[180px] flex-1">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2" style={{ color: "var(--wall-faint)" }} aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search repositories…"
            className="w-full rounded-md py-1.5 pl-8 pr-3 text-sm outline-none"
            style={{ background: "transparent", border: "1px solid var(--wall-line)", color: "var(--wall-text)" }}
          />
        </div>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setStatus(f.id)}
              aria-pressed={status === f.id}
              className="wall-focus rounded-md px-2.5 py-1.5 text-xs transition-colors"
              style={{
                color: status === f.id ? "var(--wall-text)" : "var(--wall-muted)",
                background: status === f.id ? "var(--wall-line)" : "transparent",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {shown === 0 ? (
        <p className="py-8 text-center text-sm" style={{ color: "var(--wall-faint)" }}>No scans match this filter.</p>
      ) : (
        groups.map(([day, rows]) => (
          <section key={day} className="flex flex-col gap-1">
            <div className="px-1 pb-1 pt-2 text-[11px] uppercase tracking-wide" style={{ color: "var(--wall-faint)" }}>
              {dayLabel(day)}
            </div>
            <ul className="flex flex-col gap-1">
              <AnimatePresence initial={false}>
                {rows.map((s) => {
                  const i = flatIndex++
                  const findings = findingsOf(s)
                  const running = isRunning(s)
                  const color = sevColor(s)
                  return (
                    <motion.li
                      key={s.id}
                      layout
                      initial={reduce ? false : { opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={reduce ? undefined : { opacity: 0, y: -8 }}
                      transition={{ duration: 0.25, delay: reduce ? 0 : Math.min(i, 8) * 0.03 }}
                    >
                      <button
                        onClick={() => onOpen(s.id)}
                        className="wall-focus group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-transform hover:-translate-y-0.5"
                        style={{ border: "1px solid var(--wall-line)" }}
                      >
                        <Identicon seed={s.ref} size={30} />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-mono text-sm" style={{ color: "var(--wall-text)" }}>{shortRef(s.ref)}</div>
                          <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--wall-faint)" }}>
                            <span>{s.source} · #{s.id} · {formatRelativeTime(s.created_at)}</span>
                            {running && (
                              <span className="flex items-center gap-1" style={{ color: "var(--wall-cyan)" }}>
                                <span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: "var(--wall-cyan)" }} aria-hidden />
                                scanning…
                              </span>
                            )}
                          </div>
                        </div>
                        <SeverityMicrobar s={s} />
                        <span
                          className="wall-num shrink-0 rounded px-2 py-0.5 text-xs"
                          style={{
                            color: findings > 0 ? "#04060c" : "var(--wall-muted)",
                            background: findings > 0 ? color : "var(--wall-line)",
                          }}
                        >
                          {s.status === "completed" ? (findings > 0 ? `${formatNumber(findings)} findings` : "clean") : s.status}
                        </span>
                        <ChevronRight className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5" style={{ color: "var(--wall-faint)" }} aria-hidden />
                      </button>
                    </motion.li>
                  )
                })}
              </AnimatePresence>
            </ul>
          </section>
        ))
      )}
    </div>
  )
}

function Stat({ label, value, color, pulse }: { label: string; value: string; color?: string; pulse?: boolean }) {
  return (
    <span className="flex items-baseline gap-1.5">
      {pulse && <span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: color }} aria-hidden />}
      <motion.span key={value} initial={{ opacity: 0, y: -3 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="wall-num text-base" style={{ color: color ?? "var(--wall-text)" }}>
        {value}
      </motion.span>
      <span className="text-[11px] uppercase tracking-wide" style={{ color: "var(--wall-faint)" }}>{label}</span>
    </span>
  )
}
