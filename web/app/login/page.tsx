"use client"

import dynamic from "next/dynamic"
import { SignInFlow } from "@/components/auth/SignInFlow"

// Falling-dot matrix rain; client-only (canvas + window).
const MatrixRain = dynamic(() => import("@/components/effects/MatrixRain"), { ssr: false })

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-bg">
      <MatrixRain />
      {/* darken center so the form stays legible over the warp */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(6,8,10,0.85)_0%,_rgba(6,8,10,0.4)_60%,_transparent_100%)]" />
      <div className="relative z-10 flex w-full items-center justify-center px-6">
        <SignInFlow />
      </div>
    </div>
  )
}
