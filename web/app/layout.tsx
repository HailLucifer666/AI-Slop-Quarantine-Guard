import type { Metadata } from "next"
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google"
import "./globals.css"

import { AppShell } from "@/components/layout/AppShell"

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" })
const display = Space_Grotesk({ subsets: ["latin"], variable: "--font-display", display: "swap", weight: ["600", "700"] })
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" })

export const metadata: Metadata = {
  title: "AI Slop Quarantine Guard",
  description: "PR Quality & Security Gate — automated checks for AI slop in every pull request.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${sans.variable} ${display.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-bg text-text antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
