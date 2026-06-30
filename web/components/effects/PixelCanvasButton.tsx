"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Primary CTA with a pixel-canvas hover shimmer (from the Pixel Canvas snippet).
 * The effect is a registered Web Component that animates on parent hover/focus.
 * Canvas needs concrete colors (CSS vars can't paint to canvas) → Aurora hex.
 */

class Pixel {
  ctx: CanvasRenderingContext2D
  x: number
  y: number
  color: string
  speed: number
  size = 0
  sizeStep: number
  minSize = 0.5
  maxSizeInteger = 2
  maxSize: number
  delay: number
  counter = 0
  counterStep: number
  isIdle = false
  isReverse = false
  isShimmer = false

  constructor(canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D, x: number, y: number, color: string, speed: number, delay: number) {
    this.ctx = ctx
    this.x = x
    this.y = y
    this.color = color
    this.speed = (Math.random() * 0.8 + 0.1) * speed
    this.sizeStep = Math.random() * 0.4
    this.maxSize = Math.random() * (this.maxSizeInteger - this.minSize) + this.minSize
    this.delay = delay
    this.counterStep = Math.random() * 4 + (canvas.width + canvas.height) * 0.01
  }
  draw() {
    const off = this.maxSizeInteger * 0.5 - this.size * 0.5
    this.ctx.fillStyle = this.color
    this.ctx.fillRect(this.x + off, this.y + off, this.size, this.size)
  }
  appear() {
    this.isIdle = false
    if (this.counter <= this.delay) { this.counter += this.counterStep; return }
    if (this.size >= this.maxSize) this.isShimmer = true
    if (this.isShimmer) this.shimmer()
    else this.size += this.sizeStep
    this.draw()
  }
  disappear() {
    this.isShimmer = false
    this.counter = 0
    if (this.size <= 0) { this.isIdle = true; return }
    this.size -= 0.1
    this.draw()
  }
  shimmer() {
    if (this.size >= this.maxSize) this.isReverse = true
    else if (this.size <= this.minSize) this.isReverse = false
    this.size += this.isReverse ? -this.speed : this.speed
  }
}

class PixelCanvasElement extends HTMLElement {
  private canvas = document.createElement("canvas")
  private ctx = this.canvas.getContext("2d")
  private pixels: Pixel[] = []
  private animation: number | null = null
  private timeInterval = 1000 / 60
  private timePrevious = performance.now()
  private reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  private ro: ResizeObserver | null = null
  private parent: Element | null = null
  private onEnter = () => this.handle("appear")
  private onLeave = () => this.handle("disappear")

  constructor() {
    super()
    const shadow = this.attachShadow({ mode: "open" })
    const style = document.createElement("style")
    style.textContent = ":host{display:grid;inline-size:100%;block-size:100%;overflow:hidden}"
    shadow.append(style, this.canvas)
  }
  get colors() {
    return this.dataset.colors?.split(",") || ["#16c8d4", "#4a5bff", "#2de08a"]
  }
  get gap() {
    return Math.max(4, Math.min(50, Number(this.dataset.gap) || 6))
  }
  get speed() {
    return this.reducedMotion ? 0 : Math.max(0, Math.min(100, Number(this.dataset.speed) || 35)) * 0.001
  }
  connectedCallback() {
    this.parent = this.parentElement
    requestAnimationFrame(() => {
      this.resize()
      this.ro = new ResizeObserver(() => requestAnimationFrame(() => this.resize()))
      this.ro.observe(this)
    })
    this.parent?.addEventListener("mouseenter", this.onEnter)
    this.parent?.addEventListener("mouseleave", this.onLeave)
    this.parent?.addEventListener("focus", this.onEnter, { capture: true })
    this.parent?.addEventListener("blur", this.onLeave, { capture: true })
  }
  disconnectedCallback() {
    this.ro?.disconnect()
    this.parent?.removeEventListener("mouseenter", this.onEnter)
    this.parent?.removeEventListener("mouseleave", this.onLeave)
    this.parent?.removeEventListener("focus", this.onEnter, { capture: true } as EventListenerOptions)
    this.parent?.removeEventListener("blur", this.onLeave, { capture: true } as EventListenerOptions)
    if (this.animation) cancelAnimationFrame(this.animation)
  }
  private resize() {
    if (!this.ctx) return
    const rect = this.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    const dpr = window.devicePixelRatio || 1
    this.canvas.width = Math.floor(rect.width) * dpr
    this.canvas.height = Math.floor(rect.height) * dpr
    this.canvas.style.width = `${Math.floor(rect.width)}px`
    this.canvas.style.height = `${Math.floor(rect.height)}px`
    this.ctx.setTransform(1, 0, 0, 1, 0, 0)
    this.ctx.scale(dpr, dpr)
    this.createPixels()
  }
  private dist(x: number, y: number) {
    const dx = x
    const dy = this.canvas.height - y
    return Math.sqrt(dx * dx + dy * dy)
  }
  private createPixels() {
    if (!this.ctx) return
    this.pixels = []
    for (let x = 0; x < this.canvas.width; x += this.gap) {
      for (let y = 0; y < this.canvas.height; y += this.gap) {
        const color = this.colors[Math.floor(Math.random() * this.colors.length)]
        const delay = this.reducedMotion ? 0 : this.dist(x, y)
        this.pixels.push(new Pixel(this.canvas, this.ctx, x, y, color, this.speed, delay))
      }
    }
  }
  private handle(name: "appear" | "disappear") {
    if (this.animation) cancelAnimationFrame(this.animation)
    const animate = () => {
      this.animation = requestAnimationFrame(animate)
      const now = performance.now()
      const passed = now - this.timePrevious
      if (passed < this.timeInterval) return
      this.timePrevious = now - (passed % this.timeInterval)
      if (!this.ctx) return
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
      let allIdle = true
      for (const p of this.pixels) {
        p[name]()
        if (!p.isIdle) allIdle = false
      }
      if (allIdle && this.animation) {
        cancelAnimationFrame(this.animation)
        this.animation = null
      }
    }
    animate()
  }
}

export interface PixelCanvasButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

export function PixelCanvasButton({ className, children, ...props }: PixelCanvasButtonProps) {
  React.useEffect(() => {
    if (typeof window !== "undefined" && !customElements.get("pixel-canvas")) {
      customElements.define("pixel-canvas", PixelCanvasElement)
    }
  }, [])

  return (
    <button
      className={cn(
        "group relative inline-flex min-h-[44px] items-center justify-center gap-2 overflow-hidden rounded-md bg-brand-gradient px-4 py-2 text-sm font-semibold text-bg shadow-glow transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {React.createElement("pixel-canvas", {
        "data-gap": "6",
        "data-speed": "40",
        "data-colors": "#0b0f14,#16c8d4,#4a5bff",
        style: { position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.5 },
      })}
      <span className="relative z-10 inline-flex items-center gap-2">{children}</span>
    </button>
  )
}
