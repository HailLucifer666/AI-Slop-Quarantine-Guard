"use client"

import Link from "next/link"
import { ArrowLeft } from "lucide-react"

/**
 * Page chrome for a cockpit sub-surface (Scan, Analyses, Findings, Checks,
 * Settings): a back-to-cockpit link, a title, and a centered content column.
 * The Command Wall shell (dock, ⌘K, .wall-root) is supplied by AppShell and
 * persists across navigation, so this renders only the page-specific frame.
 */
export function WallPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <div className="flex items-center gap-3 px-4 pt-3 md:px-6">
        <Link href="/dashboard" className="wall-click wall-focus flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-[color:var(--wall-muted)] transition-colors hover:text-[color:var(--wall-text)]">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Command
        </Link>
        <span className="wall-label" style={{ color: "var(--wall-text)" }}>{title}</span>
      </div>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 md:px-6">{children}</main>
    </>
  )
}
