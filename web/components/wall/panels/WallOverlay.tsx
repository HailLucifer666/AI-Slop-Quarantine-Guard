"use client"

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { motion } from "framer-motion"
import { X } from "lucide-react"

/**
 * Full-screen themed overlay shell — portalled to <body> so it escapes the wall's
 * stacking/overflow context and reliably covers the cockpit. Header + close, Esc
 * to dismiss, scrollable body. One mounts at a time (driven by usePanel).
 */
export function WallOverlay({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", on)
    return () => window.removeEventListener("keydown", on)
  }, [onClose])

  if (!mounted) return null

  return createPortal(
    <div className="fixed inset-0 z-[100] flex flex-col" role="dialog" aria-modal="true" aria-label={title}>
      <button
        aria-label="Close overlay"
        onClick={onClose}
        className="absolute inset-0 cursor-default"
        style={{ background: "rgba(2,3,10,0.94)" }}
      />
      <motion.div
        initial={{ opacity: 0, y: 14, scale: 0.99 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
        className="relative z-10 mx-auto mt-[5vh] flex h-[90vh] w-[min(1120px,94vw)] flex-col overflow-hidden rounded-xl"
        style={{ background: "var(--surface)", border: "1px solid var(--line-strong)", boxShadow: "var(--elev-2)" }}
      >
        <header className="flex shrink-0 items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid var(--line)" }}>
          <span className="wall-label" style={{ color: "var(--text)" }}>{title}</span>
          <button onClick={onClose} aria-label="Close" className="wall-focus flex h-8 w-8 items-center justify-center rounded-md transition-colors hover:brightness-150 after:absolute after:inset-0 after:-m-1.5 after:content-[''] relative" style={{ background: "var(--line)" }}>
            <X className="h-4 w-4" style={{ color: "var(--text)" }} aria-hidden />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </motion.div>
    </div>,
    document.body,
  )
}
