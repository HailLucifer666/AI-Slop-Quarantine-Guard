"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

import { WallPage } from "@/components/wall/panels/WallPage"
import { ScanConsole } from "@/components/wall/panels/ScanConsole"

/** Dedicated Scan screen. Optional ?url= pre-fills (from the ⌘K palette). */
export default function ScanPage() {
  const router = useRouter()
  const [seed, setSeed] = useState<string | undefined>(undefined)

  useEffect(() => {
    const u = new URLSearchParams(window.location.search).get("url")
    if (u) setSeed(u)
  }, [])

  return (
    <WallPage title="Scan a codebase">
      <ScanConsole initialUrl={seed} onOpenFindings={(id) => router.push(`/analyses/${id}`)} />
    </WallPage>
  )
}
