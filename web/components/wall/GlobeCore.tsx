"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useFrame } from "@react-three/fiber"
import type { ThreeEvent } from "@react-three/fiber"
import * as THREE from "three"

import { shortRef } from "@/lib/format"
import type { GlobeNode, RecentTarget } from "@/lib/useWallData"
import { SEV_HEX } from "./tokens"
import { useReducedMotion } from "./useReducedMotion"

/**
 * The live globe — a dark planet stippled with land dots sampled from a public-
 * domain NASA map. Principle (spec §6): earth = decorative brand backdrop; every
 * data layer on top is REAL — one orbit ring per recent scan (thickness ∝ files
 * scanned, color = status, click → /analyses/{id}), finding bursts sized by the
 * real findings count. The old point-to-point "traffic" arcs implied geography
 * scans don't have and are retired. Transparent canvas: floats on the starfield.
 */
const R = 1
const EARTH_URL = "/wall/earth-map.jpg"

/* Decorative brand backdrop — NOT data. These hues are identity (neon ramp);
 * every data color comes from tokens.ts SEV_HEX or the two constants below. */
const DECOR = {
  land: new THREE.Color("#6a5cf2"),
  cityCyan: new THREE.Color("#22e8e8"),
  cityMagenta: new THREE.Color("#ff3d8b"),
  atmosphere: new THREE.Color("#2b86ff"),
}
// Live-state ring color (queued | running) — the accent-cyan token value.
const LIVE_HEX = "#16e0e0"
// Failed-scan ring color — the act-failed / sev-certain token value.
const FAILED_HEX = "#ff3b5c"

function fibPoint(i: number, n: number, radius = R): THREE.Vector3 {
  const k = i + 0.5
  const phi = Math.acos(1 - (2 * k) / Math.max(1, n))
  const theta = Math.PI * (1 + Math.sqrt(5)) * k
  return new THREE.Vector3(Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta)).multiplyScalar(radius)
}

// Module-level cache of the sampled land points (plain typed arrays — cheap, no
// GPU handle). The image decode + getImageData + 30k-point loop is the expensive,
// main-thread work; caching it means every later dashboard mount rebuilds only a
// lightweight BufferGeometry instead of re-sampling, killing the navigation spike.
let earthPointsCache: { pos: Float32Array; col: Float32Array } | null = null

function buildEarthGeom(c: { pos: Float32Array; col: Float32Array }): THREE.BufferGeometry {
  const g = new THREE.BufferGeometry()
  g.setAttribute("position", new THREE.Float32BufferAttribute(c.pos, 3))
  g.setAttribute("color", new THREE.Float32BufferAttribute(c.col, 3))
  return g
}

/** Sample the earth image once (cached process-wide) → land-point geometry. */
function useEarthPoints(): THREE.BufferGeometry | null {
  // Cache hit → build the (cheap) geometry synchronously on mount.
  const [geom, setGeom] = useState<THREE.BufferGeometry | null>(() =>
    earthPointsCache ? buildEarthGeom(earthPointsCache) : null,
  )

  useEffect(() => {
    if (earthPointsCache) return // already sampled; geometry came from initial state
    let cancelled = false
    const img = new Image()
    img.crossOrigin = "anonymous"
    img.src = EARTH_URL
    img.onload = () => {
      if (cancelled) return
      const w = 512, h = 256
      const cv = document.createElement("canvas")
      cv.width = w; cv.height = h
      const ctx = cv.getContext("2d", { willReadFrequently: true })
      if (!ctx) return
      ctx.drawImage(img, 0, 0, w, h)
      const px = ctx.getImageData(0, 0, w, h).data
      // Dense sampling so continents read as solid coastlines, not a sparse haze.
      const N = 30000
      const pos: number[] = []
      const col: number[] = []
      const tmp = new THREE.Color()
      for (let i = 0; i < N; i++) {
        const p = fibPoint(i, N, R * 1.004)
        const dir = p.clone().normalize()
        const lat = Math.asin(dir.y)
        const lon = Math.atan2(dir.z, dir.x)
        const u = (lon + Math.PI) / (2 * Math.PI)
        const v = 1 - (lat + Math.PI / 2) / Math.PI
        const x = Math.min(w - 1, Math.max(0, Math.floor(u * (w - 1))))
        const y = Math.min(h - 1, Math.max(0, Math.floor(v * (h - 1))))
        const idx = (y * w + x) * 4
        const r = px[idx], g = px[idx + 1], b = px[idx + 2]
        if (!((r + g) / 2 > b + 8 && r + g + b < 690)) continue
        pos.push(p.x, p.y, p.z)
        // Mostly luminous purple land, with sparser cyan/magenta "city" clusters.
        const roll = ((i * 9301 + 49297) % 233280) / 233280
        if (roll > 0.92) tmp.copy(DECOR.cityMagenta)
        else if (roll > 0.8) tmp.copy(DECOR.cityCyan)
        else tmp.copy(DECOR.land).multiplyScalar(1.05 + roll * 0.55)
        col.push(tmp.r, tmp.g, tmp.b)
      }
      earthPointsCache = { pos: new Float32Array(pos), col: new Float32Array(col) }
      if (!cancelled) setGeom(buildEarthGeom(earthPointsCache))
    }
    return () => { cancelled = true }
  }, [])

  // Dispose this mount's geometry (the cache keeps only the raw arrays).
  useEffect(() => () => geom?.dispose(), [geom])

  return geom
}

/* ---- Data orbit rings (spec §6.1) — one per recent scan --------------------- */

function ringColor(t: RecentTarget): string {
  if (t.status === "completed") return t.clean ? SEV_HEX.clean : SEV_HEX[t.sev]
  if (t.status === "failed") return FAILED_HEX
  return LIVE_HEX
}

function buildRing(i: number, t: RecentTarget): { mesh: THREE.Mesh; proxy: THREE.Mesh } {
  const radius = 1.06 + i * 0.02 // newest innermost
  // Thickness ∝ files actually scanned (0.004–0.012 globe units).
  const tube = 0.004 + 0.008 * Math.min(1, Math.max(0, t.filesScanned) / 5000)
  // Deterministic per-index tilt — stable across polls so rings don't jump when
  // the recent list shifts.
  const tilt = new THREE.Euler(0.35 + i * 0.09, i * 0.45, 0.12 * i - 0.3)
  const pts: THREE.Vector3[] = []
  for (let s = 0; s <= 128; s++) {
    const a = (s / 128) * Math.PI * 2
    pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0))
  }
  const curve = new THREE.CatmullRomCurve3(pts, true)
  const mesh = new THREE.Mesh(
    new THREE.TubeGeometry(curve, 128, tube, 8, true),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(ringColor(t)), transparent: true, opacity: 0.45, blending: THREE.AdditiveBlending, depthWrite: false }),
  )
  mesh.rotation.copy(tilt)
  // Invisible raycast proxy (×3 radius, opacity 0) — the click/hover target.
  const proxy = new THREE.Mesh(
    new THREE.TubeGeometry(curve, 64, tube * 3, 8, true),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
  )
  proxy.rotation.copy(tilt)
  return { mesh, proxy }
}

interface SceneProps {
  nodes: GlobeNode[]
  targets: RecentTarget[]
  spin: boolean
  onHover: (idx: number | null, x: number, y: number) => void
  onOpenScan: (id: number) => void
}

function Scene({ nodes, targets, spin, onHover, onOpenScan }: SceneProps) {
  const rootRef = useRef<THREE.Group>(null)
  const earthGeom = useEarthPoints()
  const [hovered, setHovered] = useState<number | null>(null)

  const built = useMemo(() => {
    // Finding bursts — completed scans ONLY (no invented mid-scan counts); the
    // nodes list is derived from completed scans, sized by real finding counts.
    const recent = nodes.slice(-20)
    const n = Math.max(recent.length, 8)
    const pts = recent.map((node, i) => ({ node, pos: fibPoint(i, n, R * 1.01) }))

    const markers = pts.map((p) => ({
      pos: p.pos,
      color: new THREE.Color(SEV_HEX[p.node.sev]),
      size: 0.014 + Math.min(0.03, Math.sqrt(Math.max(0, p.node.weight)) * 0.004),
    }))

    // Radial glow spikes, honestly sized: length from the REAL findings count
    // (clean scans keep the 0.06 nub — sqrt(0) = 0).
    const up = new THREE.Vector3(0, 1, 0)
    const beams = pts.map((p) => {
      const dir = p.pos.clone().normalize()
      const len = 0.06 + Math.min(0.22, Math.sqrt(Math.max(0, p.node.weight)) * 0.035)
      const mid = dir.clone().multiplyScalar(R * 1.01 + len / 2)
      const geo = new THREE.CylinderGeometry(0.0015, 0.006, len, 6, 1, true)
      const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(SEV_HEX[p.node.sev]), transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false })
      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.copy(mid)
      mesh.quaternion.setFromUnitVectors(up, dir)
      return mesh
    })

    // Three ambient decorative rings (brand backdrop — opacity ≤ 0.16, not data).
    const RING_DEFS = [
      { tilt: new THREE.Euler(1.15, 0.2, 0.3), radius: R * 1.07, color: "#22e8e8", op: 0.16 },
      { tilt: new THREE.Euler(0.4, 1.2, -0.5), radius: R * 1.14, color: "#6a5cf2", op: 0.13 },
      { tilt: new THREE.Euler(-0.7, 0.6, 0.95), radius: R * 1.1, color: "#ff3d8b", op: 0.1 },
    ]
    const rings = RING_DEFS.map((d) => {
      const rp: THREE.Vector3[] = []
      for (let i = 0; i <= 128; i++) {
        const ang = (i / 128) * Math.PI * 2
        rp.push(new THREE.Vector3(Math.cos(ang) * d.radius, Math.sin(ang) * d.radius, 0))
      }
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(rp),
        new THREE.LineBasicMaterial({ color: new THREE.Color(d.color), transparent: true, opacity: d.op, blending: THREE.AdditiveBlending }),
      )
      line.setRotationFromEuler(d.tilt)
      return line
    })

    // Data orbit rings — one per recent scan (≤ 8), replacing the retired arcs.
    const dataRings = targets.map((t, i) => {
      const { mesh, proxy } = buildRing(i, t)
      return { id: t.id, mesh, proxy, live: t.status === "queued" || t.status === "running" }
    })

    return { markers, beams, rings, dataRings }
  }, [nodes, targets])

  useEffect(() => {
    return () => {
      for (const b of built.beams) { b.geometry.dispose(); (b.material as THREE.Material).dispose() }
      for (const r of built.rings) { r.geometry.dispose(); (r.material as THREE.Material).dispose() }
      for (const d of built.dataRings) {
        d.mesh.geometry.dispose(); (d.mesh.material as THREE.Material).dispose()
        d.proxy.geometry.dispose(); (d.proxy.material as THREE.Material).dispose()
      }
    }
  }, [built])

  useEffect(() => () => { document.body.style.cursor = "" }, [])

  const tRef = useRef(0)
  useFrame((_, delta) => {
    if (rootRef.current && spin) rootRef.current.rotation.y += delta * 0.05
    tRef.current = (tRef.current + delta * 0.25) % 1
    const pulse = 0.6 + 0.4 * Math.sin(tRef.current * Math.PI * 2)
    for (const b of built.beams) (b.material as THREE.MeshBasicMaterial).opacity = pulse
    // Ring opacity: hover 0.9 · queued/running pulse (0.35–0.6) · finished 0.45.
    built.dataRings.forEach((d, i) => {
      const m = d.mesh.material as THREE.MeshBasicMaterial
      if (hovered === i) m.opacity = 0.9
      else if (d.live) m.opacity = 0.35 + 0.25 * Math.sin(tRef.current * Math.PI * 2)
      else m.opacity = 0.45
    })
  })

  return (
    <group ref={rootRef} rotation={[0.32, 0, 0.08]}>
      <mesh>
        <sphereGeometry args={[R, 56, 56]} />
        <meshBasicMaterial color="#0a1126" />
      </mesh>
      <mesh>
        <sphereGeometry args={[R * 1.2, 48, 48]} />
        <meshBasicMaterial color={DECOR.atmosphere} transparent opacity={0.12} side={THREE.BackSide} blending={THREE.AdditiveBlending} />
      </mesh>

      {earthGeom && (
        <points geometry={earthGeom}>
          <pointsMaterial size={0.014} sizeAttenuation vertexColors transparent opacity={1} depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
      )}

      {built.rings.map((r, i) => <primitive key={`r${i}`} object={r} />)}

      {built.dataRings.map((d, i) => (
        <group key={`dr${d.id}`}>
          <primitive object={d.mesh} />
          <primitive
            object={d.proxy}
            onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); setHovered(i); onHover(i, e.clientX, e.clientY); document.body.style.cursor = "pointer" }}
            onPointerMove={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(i, e.clientX, e.clientY) }}
            onPointerOut={() => { setHovered(null); onHover(null, 0, 0); document.body.style.cursor = "" }}
            onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onOpenScan(d.id) }}
          />
        </group>
      ))}

      {built.markers.map((m, i) => (
        <mesh key={`m${i}`} position={m.pos}>
          <sphereGeometry args={[m.size, 8, 8]} />
          <meshBasicMaterial color={m.color} transparent blending={THREE.AdditiveBlending} />
        </mesh>
      ))}

      {built.beams.map((b, i) => <primitive key={`b${i}`} object={b} />)}
    </group>
  )
}

export default function GlobeCore({
  nodes,
  targets,
  paused = false,
  onOpenScan,
}: {
  nodes: GlobeNode[]
  targets: RecentTarget[]
  paused?: boolean
  onOpenScan: (id: number) => void
}) {
  const reduced = useReducedMotion()
  const [hidden, setHidden] = useState(false)
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null)
  useEffect(() => {
    const on = () => setHidden(document.hidden)
    document.addEventListener("visibilitychange", on)
    return () => document.removeEventListener("visibilitychange", on)
  }, [])
  const spin = !paused && !reduced && !hidden

  const handleHover = useCallback(
    (idx: number | null, x: number, y: number) => {
      if (idx == null) { setTip(null); return }
      const t = targets[idx]
      if (!t) { setTip(null); return }
      setTip({
        x, y,
        text: `scan/${t.id} · ${shortRef(t.ref)} · ${t.status} · ${t.filesScanned} files · ${t.findings} findings`,
      })
    },
    [targets],
  )

  return (
    <div className="relative h-full w-full" aria-hidden>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 0, 3.15], fov: 40 }}
        frameloop={spin ? "always" : "demand"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        onPointerMissed={() => setTip(null)}
      >
        <Scene nodes={nodes} targets={targets} spin={spin} onHover={handleHover} onOpenScan={onOpenScan} />
      </Canvas>
      {tip && (
        <div className="wall-tooltip" style={{ left: tip.x + 12, top: tip.y + 12 }}>
          {tip.text}
        </div>
      )}
    </div>
  )
}
