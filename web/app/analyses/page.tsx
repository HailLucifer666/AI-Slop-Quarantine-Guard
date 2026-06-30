"use client"

import { useRouter } from "next/navigation"

import { WallPage } from "@/components/wall/panels/WallPage"
import { AnalysesExplorer } from "@/components/wall/panels/AnalysesExplorer"

/** Dedicated Analyses screen — every scan, newest first. */
export default function AnalysesPage() {
  const router = useRouter()
  return (
    <WallPage title="Analyses">
      <AnalysesExplorer onOpen={(id) => router.push(`/analyses/${id}`)} />
    </WallPage>
  )
}
