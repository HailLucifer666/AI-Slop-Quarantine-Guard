"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useFrame } from "@react-three/fiber"
import * as THREE from "three"

import type { GlobeNode, Sev } from "@/lib/useWallData"
import { useReducedMotion } from "./useReducedMotion"

/**
 * The live globe — a dark planet stippled with land dots sampled from a
 * public-domain NASA map, with great-circle arcs + volumetric beams driven by the
 * REAL scan stream. Nodes are placed deterministically (fibonacci) — abstract,
 * not geographic. Transparent canvas: it floats on the page starfield.
 */
const R = 1
const EARTH_URL = "/wall/earth-map.jpg"

const C = {
  land: new THREE.Color("#6a5cf2"),
  cityCyan: new THREE.Color("#22e8e8"),
  cityMagenta: new THREE.Color("#ff3d8b"),
  atmosphere: new THREE.Color("#2b86ff"),
  arcDot: new THREE.Color("#22e8e8"),
}
const SEV_HEX: Record<Sev, string> = {
  certain: "#ff3b5c",
  high: "#ff8a3d",
  medium: "#ffc83d",
  clean: "#22e8e8",
}

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
        if (roll > 0.92) tmp.copy(C.cityMagenta)
        else if (roll > 0.8) tmp.copy(C.cityCyan)
        else tmp.copy(C.land).multiplyScalar(1.05 + roll * 0.55)
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

function Scene({ nodes, spin }: { nodes: GlobeNode[]; spin: boolean }) {
  const rootRef = useRef<THREE.Group>(null)
  const earthGeom = useEarthPoints()

  const built = useMemo(() => {
    const recent = nodes.slice(-20)
    const n = Math.max(recent.length, 8)
    const pts = recent.map((node, i) => ({ node, pos: fibPoint(i, n, R * 1.01) }))

    const markers = pts.map((p) => ({ pos: p.pos, color: new THREE.Color(SEV_HEX[p.node.sev]) }))

    // Short radial glow spikes — clustered at active points, not long rods.
    const up = new THREE.Vector3(0, 1, 0)
    const beams = pts.map((p) => {
      const dir = p.pos.clone().normalize()
      const len = p.node.sev === "clean" ? 0.07 : 0.12 + Math.min(0.18, p.node.weight * 0.02)
      const mid = dir.clone().multiplyScalar(R * 1.01 + len / 2)
      const geo = new THREE.CylinderGeometry(0.0015, 0.006, len, 6, 1, true)
      const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(SEV_HEX[p.node.sev]), transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false })
      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.copy(mid)
      mesh.quaternion.setFromUnitVectors(up, dir)
      return mesh
    })

    // Great-circle arcs: slerp from A to B along the surface, lifted by a sine
    // profile so they bow above it and land back down — both ends pinned, never
    // crossing through the centre. (A raised-midpoint bezier degenerates to a
    // straight chord when the two points are near-antipodal.)
    const arcDotMat = new THREE.MeshBasicMaterial({ color: C.arcDot, transparent: true, blending: THREE.AdditiveBlending })
    const arcs: { line: THREE.Line; curve: THREE.CatmullRomCurve3; dot: THREE.Mesh }[] = []
    const SEGS = 48
    for (let i = 1; i < pts.length; i++) {
      const da = pts[i - 1].pos.clone().normalize()
      const db = pts[i].pos.clone().normalize()
      const ang = da.angleTo(db)
      if (ang < 0.05) continue // coincident — nothing to connect
      const sinAng = Math.sin(ang)
      const frac = ang / Math.PI // 0 (near) → 1 (antipodal)
      const lift = 0.22 + 0.45 * frac
      const arcPts: THREE.Vector3[] = []
      for (let s = 0; s <= SEGS; s++) {
        const t = s / SEGS
        const w1 = Math.sin((1 - t) * ang) / sinAng
        const w2 = Math.sin(t * ang) / sinAng
        const dir = da.clone().multiplyScalar(w1).add(db.clone().multiplyScalar(w2)).normalize()
        const h = R * 1.01 + Math.sin(Math.PI * t) * lift
        arcPts.push(dir.multiplyScalar(h))
      }
      const curve = new THREE.CatmullRomCurve3(arcPts)
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(arcPts),
        new THREE.LineBasicMaterial({ color: new THREE.Color(SEV_HEX[pts[i].node.sev]), transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending }),
      )
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.013, 8, 8), arcDotMat)
      dot.position.copy(arcPts[0])
      arcs.push({ line, curve, dot })
    }

    // Ambient orbital great-circle rings (static, for the layered-depth look).
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

    return { markers, beams, arcs, arcDotMat, rings }
  }, [nodes])

  useEffect(() => {
    return () => {
      for (const a of built.arcs) { a.line.geometry.dispose(); (a.line.material as THREE.Material).dispose(); a.dot.geometry.dispose() }
      built.arcDotMat.dispose()
      for (const b of built.beams) { b.geometry.dispose(); (b.material as THREE.Material).dispose() }
      for (const r of built.rings) { r.geometry.dispose(); (r.material as THREE.Material).dispose() }
    }
  }, [built])

  const tRef = useRef(0)
  useFrame((_, delta) => {
    if (rootRef.current && spin) rootRef.current.rotation.y += delta * 0.05
    tRef.current = (tRef.current + delta * 0.25) % 1
    for (let i = 0; i < built.arcs.length; i++) {
      const local = (tRef.current + i / Math.max(1, built.arcs.length)) % 1
      built.arcs[i].curve.getPoint(local, built.arcs[i].dot.position)
    }
    const pulse = 0.6 + 0.4 * Math.sin(tRef.current * Math.PI * 2)
    for (const b of built.beams) (b.material as THREE.MeshBasicMaterial).opacity = pulse
  })

  return (
    <group ref={rootRef} rotation={[0.32, 0, 0.08]}>
      <mesh>
        <sphereGeometry args={[R, 56, 56]} />
        <meshBasicMaterial color="#0a1126" />
      </mesh>
      <mesh>
        <sphereGeometry args={[R * 1.2, 48, 48]} />
        <meshBasicMaterial color={C.atmosphere} transparent opacity={0.12} side={THREE.BackSide} blending={THREE.AdditiveBlending} />
      </mesh>

      {earthGeom && (
        <points geometry={earthGeom}>
          <pointsMaterial size={0.014} sizeAttenuation vertexColors transparent opacity={1} depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
      )}

      {built.rings.map((r, i) => <primitive key={`r${i}`} object={r} />)}

      {built.markers.map((m, i) => (
        <mesh key={`m${i}`} position={m.pos}>
          <sphereGeometry args={[0.018, 8, 8]} />
          <meshBasicMaterial color={m.color} transparent blending={THREE.AdditiveBlending} />
        </mesh>
      ))}

      {built.beams.map((b, i) => <primitive key={`b${i}`} object={b} />)}

      {built.arcs.map((a, i) => (
        <group key={`a${i}`}>
          <primitive object={a.line} />
          <primitive object={a.dot} />
        </group>
      ))}
    </group>
  )
}

export default function GlobeCore({ nodes, paused = false }: { nodes: GlobeNode[]; paused?: boolean }) {
  const reduced = useReducedMotion()
  const [hidden, setHidden] = useState(false)
  useEffect(() => {
    const on = () => setHidden(document.hidden)
    document.addEventListener("visibilitychange", on)
    return () => document.removeEventListener("visibilitychange", on)
  }, [])
  const spin = !paused && !reduced && !hidden
  return (
    <div className="h-full w-full">
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 0, 3.15], fov: 40 }}
        frameloop={spin ? "always" : "demand"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        aria-label="Live globe of scan activity"
      >
        <Scene nodes={nodes} spin={spin} />
      </Canvas>
    </div>
  )
}
