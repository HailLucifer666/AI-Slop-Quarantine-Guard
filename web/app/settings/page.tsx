"use client"

import { WallPage } from "@/components/wall/panels/WallPage"
import { SettingsPanel } from "@/components/wall/panels/SettingsPanel"

/** Dedicated Settings screen. */
export default function SettingsPage() {
  return (
    <WallPage title="Settings">
      <SettingsPanel />
    </WallPage>
  )
}
