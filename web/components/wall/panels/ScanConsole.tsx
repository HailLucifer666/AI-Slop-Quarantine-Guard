"use client"

import { useCallback, useRef, useState } from "react"
import { ArrowUpRight, FileArchive, FolderOpen, Github, Loader2, ScanLine } from "lucide-react"

import { getScan, startLocalScan, startUrlScan, startZipScan } from "@/lib/api"
import { isTerminal, type ScanDetail } from "@/lib/types"
import { cn } from "@/lib/utils"
import { ActivitySpectrum } from "./ActivitySpectrum"
import { AnimatedScan } from "./AnimatedScan"
import { ScanResults } from "./ScanResults"

type Mode = "url" | "zip" | "local"
const POLL_MS = 1500
const TIMEOUT_MS = 120000
const TABS: { id: Mode; label: string; icon: typeof Github }[] = [
  { id: "url", label: "Public URL", icon: Github },
  { id: "zip", label: "Upload .zip", icon: FileArchive },
  { id: "local", label: "Local folder", icon: FolderOpen },
]

/** Translate raw backend/git errors into plain English for non-technical users. */
function friendlyError(raw: string): string {
  const e = raw.toLowerCase()
  if (e.includes("not found") || e.includes("404"))
    return "We couldn't find that repository. Check the URL is exact and that the repo is public — private repos need sign-in, which the public-URL scan doesn't support yet."
  if (e.includes("could not resolve") || e.includes("network") || e.includes("timed out") || e.includes("connection"))
    return "Couldn't reach GitHub to download the repository. Check the URL and your connection, then try again."
  if (e.includes("clone failed") || e.includes("git "))
    return "Couldn't download that repository. Double-check the URL points to a real, public repo."
  return raw
}

/**
 * Scan console — HUD input + the live Activity Spectrum. Starts a REAL scan and
 * polls it; the spectrum animates while running and settles on completion, then
 * offers the Findings overlay. No fake progress.
 */
export function ScanConsole({ initialUrl, onOpenFindings }: { initialUrl?: string; onOpenFindings: (id: number) => void }) {
  const [mode, setMode] = useState<Mode>("url")
  const [url, setUrl] = useState(initialUrl ?? "")
  const [path, setPath] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [scan, setScan] = useState<ScanDetail | null>(null)
  const [phase, setPhase] = useState("")
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const poll = useCallback(async (id: number) => {
    const deadline = Date.now() + TIMEOUT_MS
    while (Date.now() < deadline) {
      const s = await getScan(id)
      setScan(s)
      setPhase(s.status === "running" ? "Analyzing codebase…" : s.status === "queued" ? "Queued…" : "")
      if (isTerminal(s.status)) return s
      await new Promise((r) => setTimeout(r, POLL_MS))
    }
    throw new Error("Still running in the background — check Analyses for the result.")
  }, [])

  async function run() {
    setError(null)
    setBusy(true)
    setScan(null)
    setPhase("Starting…")
    try {
      let id: number
      if (mode === "url") {
        if (!url.trim()) throw new Error("Paste a repository URL first.")
        id = (await startUrlScan(url.trim())).scan_id
      } else if (mode === "local") {
        if (!path.trim()) throw new Error("Enter a local folder path.")
        id = (await startLocalScan(path.trim())).scan_id
      } else {
        if (!file) throw new Error("Choose a .zip file first.")
        id = (await startZipScan(file)).scan_id
      }
      await poll(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.")
    } finally {
      setBusy(false)
      setPhase("")
    }
  }

  const counts = scan?.analytics?.by_rule ?? {}
  const active = busy && (!scan || scan.status === "running" || scan.status === "queued")

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Scan source">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} role="tab" aria-selected={mode === id} onClick={() => setMode(id)} disabled={busy} className={cn("wall-tab", mode === id && "wall-tab-on")}>
            <Icon className="h-4 w-4" aria-hidden /> {label}
          </button>
        ))}
      </div>

      {mode === "url" && (
        <input className="wall-input" placeholder="https://github.com/owner/repo" value={url} onChange={(e) => setUrl(e.target.value)} disabled={busy} onKeyDown={(e) => e.key === "Enter" && !busy && run()} />
      )}
      {mode === "local" && (
        <div className="flex flex-col gap-1.5">
          <input className="wall-input" placeholder="C:\path\to\project  ·  /home/you/project" value={path} onChange={(e) => setPath(e.target.value)} disabled={busy} />
          <p className="text-xs" style={{ color: "var(--text-faint)" }}>Full path to a folder on the machine running the scanner (Windows or Unix style).</p>
        </div>
      )}
      {mode === "zip" && (
        <div className="flex items-center gap-3">
          <button onClick={() => fileInput.current?.click()} disabled={busy} className="wall-tab">
            <FileArchive className="h-4 w-4" aria-hidden /> {file ? file.name : "Choose .zip"}
          </button>
          {file && !busy && (
            <button onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = "" }} className="wall-click wall-focus inline-flex min-h-[44px] items-center text-sm" style={{ color: "var(--text-muted)" }}>
              Clear
            </button>
          )}
          <input ref={fileInput} type="file" accept=".zip,application/zip" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
      )}

      {error && <p role="alert" className="text-sm" style={{ color: "var(--sev-certain)" }}>{error}</p>}

      <button onClick={run} disabled={busy} className="wall-cta">
        {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {phase || "Working…"}</> : <><ScanLine className="h-4 w-4" aria-hidden /> Run scan</>}
      </button>

      <div className="flex flex-col gap-3 rounded-xl p-4" style={{ border: "1px solid var(--line)" }}>
        <div className="wall-label">Activity</div>
        <AnimatedScan
          status={scan?.status ?? (busy ? "queued" : "idle")}
          progress={scan?.progress}
          startedAt={scan?.created_at}
          filesScanned={scan?.analytics?.files_scanned ?? null}
          active={active}
        />
        <div className="h-[360px] overflow-hidden">
          <ActivitySpectrum active={active} counts={counts} />
        </div>
      </div>

      {scan?.status === "completed" && (
        <div className="space-y-4">
          <ScanResults scan={scan} />
          <button onClick={() => onOpenFindings(scan.id)} className="wall-click wall-focus inline-flex min-h-[44px] items-center text-sm" style={{ color: "var(--text-muted)" }}>
            Open full report <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      )}
      {scan?.status === "failed" && (
        <div role="alert" className="rounded-md p-3 text-sm" style={{ color: "var(--sev-certain)", background: "rgba(255,59,92,0.07)", border: "1px solid rgba(255,59,92,0.22)" }}>
          <p>{friendlyError(scan.error ?? "unknown error")}</p>
          {scan.error && <p className="mt-1.5 font-mono text-xs" style={{ color: "var(--text-faint)" }}>Details: {scan.error}</p>}
        </div>
      )}
    </div>
  )
}
