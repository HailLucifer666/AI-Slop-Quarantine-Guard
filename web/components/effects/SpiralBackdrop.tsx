"use client"

import { useEffect, useRef } from "react"

type Gsap = (typeof import("gsap"))["gsap"]

/**
 * Fullscreen 2D-canvas spiral particle warp (login backdrop). Adapted from the
 * supplied Spiral Animation snippet. SSR-safe: gsap is lazy-imported inside the
 * effect (the snippet's module-level gsap import + `window` access are fatal to
 * Next's build), and the whole component is loaded dynamic({ ssr:false }).
 * Under reduced-motion it paints one static frame and never starts the timeline.
 */

class Vector2D {
  constructor(public x: number, public y: number) {}
  static random(min: number, max: number): number {
    return min + Math.random() * (max - min)
  }
}
class Vector3D {
  constructor(public x: number, public y: number, public z: number) {}
}

class Star {
  private dx: number
  private dy: number
  private spiralLocation: number
  private strokeWeightFactor: number
  private z: number
  private angle: number
  private distance: number
  private rotationDirection: number
  private expansionRate: number
  private finalScale: number

  constructor(cameraZ: number, cameraTravelDistance: number) {
    this.angle = Math.random() * Math.PI * 2
    this.distance = 30 * Math.random() + 15
    this.rotationDirection = Math.random() > 0.5 ? 1 : -1
    this.expansionRate = 1.2 + Math.random() * 0.8
    this.finalScale = 0.7 + Math.random() * 0.6
    this.dx = this.distance * Math.cos(this.angle)
    this.dy = this.distance * Math.sin(this.angle)
    this.spiralLocation = (1 - Math.pow(1 - Math.random(), 3.0)) / 1.3
    this.z = Vector2D.random(0.5 * cameraZ, cameraTravelDistance + cameraZ)
    const lerp = (s: number, e: number, t: number) => s * (1 - t) + e * t
    this.z = lerp(this.z, cameraTravelDistance / 2, 0.3 * this.spiralLocation)
    this.strokeWeightFactor = Math.pow(Math.random(), 2.0)
  }

  render(p: number, c: AnimationController) {
    const spiralPos = c.spiralPath(this.spiralLocation)
    const q = p - this.spiralLocation
    if (q <= 0) return
    const dp = c.constrain(4 * q, 0, 1)
    const powerEasing = Math.pow(dp, 2)
    const elasticEasing = c.easeOutElastic(dp)
    let screenX: number
    let screenY: number
    if (dp < 0.3) {
      const easing = c.lerp(dp, powerEasing, dp / 0.3)
      screenX = c.lerp(spiralPos.x, spiralPos.x + this.dx * 0.3, easing / 0.3)
      screenY = c.lerp(spiralPos.y, spiralPos.y + this.dy * 0.3, easing / 0.3)
    } else if (dp < 0.7) {
      const mid = (dp - 0.3) / 0.4
      const curve = Math.sin(mid * Math.PI) * this.rotationDirection * 1.5
      const baseX = spiralPos.x + this.dx * 0.3
      const baseY = spiralPos.y + this.dy * 0.3
      const targetX = spiralPos.x + this.dx * 0.7
      const targetY = spiralPos.y + this.dy * 0.7
      const perpX = -this.dy * 0.4 * curve
      const perpY = this.dx * 0.4 * curve
      screenX = c.lerp(baseX, targetX, mid) + perpX * mid
      screenY = c.lerp(baseY, targetY, mid) + perpY * mid
    } else {
      const fin = (dp - 0.7) / 0.3
      const baseX = spiralPos.x + this.dx * 0.7
      const baseY = spiralPos.y + this.dy * 0.7
      const targetDistance = this.distance * this.expansionRate * 1.5
      const spiralAngle = this.angle + 1.2 * this.rotationDirection * fin * Math.PI
      const targetX = spiralPos.x + targetDistance * Math.cos(spiralAngle)
      const targetY = spiralPos.y + targetDistance * Math.sin(spiralAngle)
      screenX = c.lerp(baseX, targetX, fin)
      screenY = c.lerp(baseY, targetY, fin)
    }
    const vx = ((this.z - c.cameraZ) * screenX) / c.viewZoom
    const vy = ((this.z - c.cameraZ) * screenY) / c.viewZoom
    let sizeMultiplier = 1.0
    if (dp < 0.6) sizeMultiplier = 1.0 + dp * 0.2
    else {
      const t = (dp - 0.6) / 0.4
      sizeMultiplier = 1.2 * (1.0 - t) + this.finalScale * t
    }
    c.showProjectedDot(new Vector3D(vx, vy, this.z), 8.5 * this.strokeWeightFactor * sizeMultiplier)
  }
}

class AnimationController {
  private timeline: ReturnType<Gsap["timeline"]> | null = null
  private time = 0
  private ctx: CanvasRenderingContext2D
  private size: number
  private stars: Star[] = []
  readonly cameraZ = -400
  private readonly cameraTravelDistance = 3400
  private readonly startDotYOffset = 28
  readonly viewZoom = 100
  private readonly numberOfStars = 4000
  private readonly trailLength = 80
  private readonly changeEventTime = 0.32

  constructor(
    ctx: CanvasRenderingContext2D,
    size: number,
    gsapInstance: Gsap,
    play: boolean,
  ) {
    this.ctx = ctx
    this.size = size
    this.createStars()
    if (play) {
      this.timeline = gsapInstance.timeline({ repeat: -1 })
      this.timeline.to(this, { time: 1, duration: 15, ease: "none", onUpdate: () => this.render() })
    } else {
      this.time = 0.45
      this.render()
    }
  }

  private createStars() {
    for (let i = 0; i < this.numberOfStars; i++)
      this.stars.push(new Star(this.cameraZ, this.cameraTravelDistance))
  }

  ease(p: number, g: number): number {
    return p < 0.5 ? 0.5 * Math.pow(2 * p, g) : 1 - 0.5 * Math.pow(2 * (1 - p), g)
  }
  easeOutElastic(x: number): number {
    const c4 = (2 * Math.PI) / 4.5
    if (x <= 0) return 0
    if (x >= 1) return 1
    return Math.pow(2, -8 * x) * Math.sin((x * 8 - 0.75) * c4) + 1
  }
  map(v: number, s1: number, e1: number, s2: number, e2: number): number {
    return s2 + (e2 - s2) * ((v - s1) / (e1 - s1))
  }
  constrain(v: number, min: number, max: number): number {
    return Math.min(Math.max(v, min), max)
  }
  lerp(s: number, e: number, t: number): number {
    return s * (1 - t) + e * t
  }
  spiralPath(p: number): Vector2D {
    p = this.constrain(1.2 * p, 0, 1)
    p = this.ease(p, 1.8)
    const theta = 2 * Math.PI * 6 * Math.sqrt(p)
    const r = 170 * Math.sqrt(p)
    return new Vector2D(r * Math.cos(theta), r * Math.sin(theta) + this.startDotYOffset)
  }
  showProjectedDot(position: Vector3D, sizeFactor: number) {
    const t2 = this.constrain(this.map(this.time, this.changeEventTime, 1, 0, 1), 0, 1)
    const newCameraZ = this.cameraZ + this.ease(Math.pow(t2, 1.2), 1.8) * this.cameraTravelDistance
    if (position.z <= newCameraZ) return
    const depth = position.z - newCameraZ
    const x = (this.viewZoom * position.x) / depth
    const y = (this.viewZoom * position.y) / depth
    this.ctx.beginPath()
    this.ctx.arc(x, y, 0.5, 0, Math.PI * 2)
    this.ctx.fill()
  }
  render() {
    const ctx = this.ctx
    ctx.fillStyle = "#06080a"
    ctx.fillRect(0, 0, this.size, this.size)
    ctx.save()
    ctx.translate(this.size / 2, this.size / 2)
    const t1 = this.constrain(this.map(this.time, 0, this.changeEventTime + 0.25, 0, 1), 0, 1)
    const t2 = this.constrain(this.map(this.time, this.changeEventTime, 1, 0, 1), 0, 1)
    ctx.rotate(-Math.PI * this.ease(t2, 2.7))
    ctx.fillStyle = "#16c8d4"
    for (let i = 0; i < this.trailLength; i++) {
      const f = this.map(i, 0, this.trailLength, 1.1, 0.1)
      const sw = (1.3 * (1 - t1) + 3.0 * Math.sin(Math.PI * t1)) * f
      const pos = this.spiralPath(t1 - 0.00015 * i)
      this.ctx.beginPath()
      this.ctx.arc(pos.x, pos.y, sw / 2, 0, Math.PI * 2)
      this.ctx.fill()
    }
    ctx.fillStyle = "#eaeef6"
    for (const star of this.stars) star.render(t1, this)
    ctx.restore()
  }
  destroy() {
    this.timeline?.kill()
    this.timeline = null
  }
}

export default function SpiralBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let controller: AnimationController | null = null
    let gsapInstance: Gsap | null = null
    let disposed = false
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false

    const build = () => {
      if (disposed || !gsapInstance) return
      controller?.destroy()
      const dpr = window.devicePixelRatio || 1
      const size = Math.max(window.innerWidth, window.innerHeight)
      canvas.width = size * dpr
      canvas.height = size * dpr
      canvas.style.width = `${window.innerWidth}px`
      canvas.style.height = `${window.innerHeight}px`
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.scale(dpr, dpr)
      controller = new AnimationController(ctx, size, gsapInstance, !reduce)
    }

    import("gsap").then((m) => {
      gsapInstance = (m.gsap ?? m.default) as Gsap
      build()
    })

    let raf = 0
    const onResize = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(build)
    }
    window.addEventListener("resize", onResize)
    return () => {
      disposed = true
      window.removeEventListener("resize", onResize)
      cancelAnimationFrame(raf)
      controller?.destroy()
    }
  }, [])

  return (
    <div aria-hidden className="absolute inset-0 h-full w-full overflow-hidden">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
    </div>
  )
}
