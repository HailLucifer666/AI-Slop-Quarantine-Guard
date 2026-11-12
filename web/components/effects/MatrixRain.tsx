"use client"

import { useEffect, useRef } from "react"

import { useReducedMotion } from "@/components/wall/useReducedMotion"

/**
 * Falling-dot matrix rain — original 2D-canvas implementation (the reference txt
 * was empty). Neon cyan/violet trails on near-black; DPR-capped for 4K crispness,
 * 60fps, GPU-light (no WebGL). Pauses when hidden; reduced-motion → static field.
 */
const GLYPHS = "01<>/\\[]{}#*+·:".split("")

export default function MatrixRain() {
  const ref = useRef<HTMLCanvasElement>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let cols = 0
    let drops: number[] = []
    let font = 15

    const setup = () => {
      canvas.width = window.innerWidth * dpr
      canvas.height = window.innerHeight * dpr
      font = Math.round(15 * dpr)
      cols = Math.ceil(canvas.width / font)
      drops = Array.from({ length: cols }, () => Math.random() * -60)
    }
    setup()
    const onResize = () => setup()
    window.addEventListener("resize", onResize)

    let hidden = document.hidden
    const onVis = () => {
      hidden = document.hidden
    }
    document.addEventListener("visibilitychange", onVis)

    let raf = 0
    const step = () => {
      if (!hidden) {
        ctx.fillStyle = "rgba(4,6,12,0.10)"
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.font = `${font}px monospace`
        for (let i = 0; i < cols; i++) {
          const x = i * font
          const y = drops[i] * font
          ctx.fillStyle = i % 3 === 0 ? "#16e0e0" : "#8b5cf6" // --accent-cyan / --accent-violet (hex: canvas can't read CSS vars)
          ctx.globalAlpha = 0.85
          ctx.fillText(GLYPHS[(Math.random() * GLYPHS.length) | 0], x, y)
          ctx.globalAlpha = 1
          if (y > canvas.height && Math.random() > 0.97) drops[i] = Math.random() * -20
          drops[i] += 0.55
        }
      }
      raf = requestAnimationFrame(step)
    }

    if (reduced) {
      ctx.fillStyle = "#04060c"
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.font = `${font}px monospace`
      const rows = Math.ceil(canvas.height / (font * 1.6))
      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          if (Math.random() > 0.9) {
            ctx.fillStyle = i % 3 === 0 ? "rgba(22,224,224,0.22)" : "rgba(139,92,246,0.2)"
            ctx.fillText(GLYPHS[(Math.random() * GLYPHS.length) | 0], i * font, j * font * 1.6)
          }
        }
      }
    } else {
      raf = requestAnimationFrame(step)
    }

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", onResize)
      document.removeEventListener("visibilitychange", onVis)
    }
  }, [reduced])

  return <canvas ref={ref} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />
}
