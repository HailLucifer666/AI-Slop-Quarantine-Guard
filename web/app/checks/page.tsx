"use client"

import { WallPage } from "@/components/wall/panels/WallPage"
import { ChecksCatalog } from "@/components/wall/panels/ChecksCatalog"

/** Dedicated Checks catalog screen. */
export default function ChecksPage() {
  return (
    <WallPage title="Checks">
      <ChecksCatalog />
    </WallPage>
  )
}
