"use client"

import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"

import { getSettings, updateSettings } from "@/lib/api"
import { CHECKS } from "@/lib/checks"
import type { AppSettings } from "@/lib/types"

const RULES = Object.keys(CHECKS)
const RETENTION = [30, 90, 365]

/** Settings overlay — block mode, blocked rules, retention; persists via PATCH. */
export function SettingsPanel() {
  const [s, setS] = useState<AppSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getSettings().then(setS).catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
  }, [])

  async function patch(p: Partial<AppSettings>) {
    if (!s) return
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const next = await updateSettings(p)
      setS(next)
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  if (error) return <p className="text-sm" style={{ color: "var(--wall-act-failed)" }}>{error}</p>
  if (!s) return <p className="flex items-center gap-2 text-sm" style={{ color: "var(--wall-muted)" }}><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>

  const toggleRule = (id: string) => {
    const set = new Set(s.blocked_rules)
    if (set.has(id)) set.delete(id)
    else set.add(id)
    patch({ blocked_rules: [...set] })
  }

  return (
    <div className="max-w-2xl space-y-7">
      <section className="wall-card flex items-center justify-between p-5">
        <div>
          <div className="font-display text-base font-semibold" style={{ color: "var(--wall-text)" }}>Block mode</div>
          <p className="mt-1 text-sm" style={{ color: "var(--wall-muted)" }}>Saved preference only — enforcement ships in a later phase (the Guard stays advisory).</p>
        </div>
        <button
          role="switch"
          aria-checked={s.block_mode}
          onClick={() => patch({ block_mode: !s.block_mode })}
          className="wall-focus relative h-6 w-11 shrink-0 rounded-full transition-colors"
          style={{ background: s.block_mode ? "var(--wall-green)" : "var(--wall-line-strong)" }}
        >
          <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all" style={{ left: s.block_mode ? 22 : 2 }} />
        </button>
      </section>

      <section className="wall-card p-5">
        <div className="font-display text-base font-semibold" style={{ color: "var(--wall-text)" }}>Blocked rules</div>
        <p className="mb-3 mt-1 text-sm" style={{ color: "var(--wall-muted)" }}>Which checks would block when enforcement is on.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {RULES.map((id) => {
            const on = s.blocked_rules.includes(id)
            return (
              <button key={id} onClick={() => toggleRule(id)} title={CHECKS[id]?.blurb} className="wall-focus flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm" style={{ border: `1px solid ${on ? "var(--wall-cyan)" : "var(--wall-line)"}`, color: "var(--wall-text)" }}>
                <span className="h-2 w-2 rounded-full" style={{ background: on ? "var(--wall-cyan)" : "var(--wall-line-strong)" }} aria-hidden />
                <span className="font-mono text-xs" style={{ color: "var(--wall-faint)" }}>{id}</span>
                <span className="truncate">{CHECKS[id]?.name}</span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="wall-card p-5">
        <div className="font-display text-base font-semibold" style={{ color: "var(--wall-text)" }}>Retention</div>
        <p className="mb-3 mt-1 text-sm" style={{ color: "var(--wall-muted)" }}>Scans older than this are deleted automatically.</p>
        <div className="flex gap-2">
          {RETENTION.map((d) => (
            <button key={d} onClick={() => patch({ retention_days: d })} className="wall-focus rounded-md px-4 py-2 text-sm" style={{ border: `1px solid ${s.retention_days === d ? "var(--wall-cyan)" : "var(--wall-line)"}`, color: s.retention_days === d ? "var(--wall-text)" : "var(--wall-muted)" }}>
              {d} days
            </button>
          ))}
        </div>
      </section>

      <div className="text-xs" style={{ color: saved ? "var(--wall-green)" : "var(--wall-faint)" }}>
        {saving ? "Saving…" : saved ? "Saved." : "Changes save automatically."}
      </div>
    </div>
  )
}
