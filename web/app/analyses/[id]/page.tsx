"use client"

import { useParams } from "next/navigation"

import { WallPage } from "@/components/wall/panels/WallPage"
import { FindingsView } from "@/components/wall/panels/FindingsView"

/** Dedicated per-scan Findings screen. */
export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>()
  return (
    <WallPage title={`Findings · #${id}`}>
      <FindingsView id={id} />
    </WallPage>
  )
}
