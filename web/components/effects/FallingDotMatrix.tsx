"use client"

import { useEffect, useRef } from "react"

/**
 * Falling dot-matrix background — Matrix-style rain made of dots, not characters.
 * Columns of dots cascade downward with a fading trail (brightest at the head),
 * recoloured to Aurora teal + indigo. Plain 2D canvas (no WebGL/shader) so it
 * renders reliably as a global page backdrop. Honours prefers-reduced-motion
 * (renders nothing) and is purely decorative (aria-hidden, pointer-events-none).
 */

const TEAL = "22,200,212"
const INDIGO = "74,91,255"
const CELL = 22 // px grid spacing between dots

type Column = { y: number; speed: number; len: number; color: string }

function makeColumn(height: number, startAbove: boolean): Column {
  return {
    y: startAbove ? -Math.random() * height : Math.random() * height,
    speed: 45 + Math.random() * 95, // px per second
    len: 6 + Math.floor(Math.random() * 14), // dots in the trail
    color: Math.random() < 0.5 ? TEAL : INDIGO,
  }
}

export default function FallingDotMatrix() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return
    const canvas = ref.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    let columns: Column[] = []
    let raf = 0

    const setup = () => {
      w = canvas.clientWidth
      h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      columns = Array.from({ length: Math.ceil(w / CELL) }, () => makeColumn(h, false))
    }

    setup()
    window.addEventListener("resize", setup)

    let last = performance.now()
    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05)
      last = now
      ctx.clearRect(0, 0, w, h)

      for (let i = 0; i < columns.length; i++) {
        const c = columns[i]
        c.y += c.speed * dt
        const x = i * CELL + CELL / 2
        const headRow = Math.floor(c.y / CELL)

        for (let k = 0; k < c.len; k++) {
          const yy = (headRow - k) * CELL + CELL / 2
          if (yy < 0 || yy > h) continue
          const alpha = (1 - k / c.len) * 0.9
          ctx.fillStyle = `rgba(${c.color},${alpha.toFixed(3)})`
          ctx.beginPath()
          ctx.arc(x, yy, k === 0 ? 1.9 : 1.3, 0, Math.PI * 2)
          ctx.fill()
        }

        // Recycle to the top once the whole trail has fallen past the bottom.
        if ((headRow - c.len) * CELL > h) columns[i] = makeColumn(h, true)
      }

      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", setup)
    }
  }, [])

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-[9] h-full w-full"
      style={{
        maskImage: "radial-gradient(circle at 50% 35%, black 60%, transparent 96%)",
        WebkitMaskImage: "radial-gradient(circle at 50% 35%, black 60%, transparent 96%)",
      }}
    />
  )
}
