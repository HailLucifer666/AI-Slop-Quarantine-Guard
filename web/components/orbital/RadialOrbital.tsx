"use client"

import { useEffect, useRef, useState } from "react"
import { Bug, FileCode2, KeyRound, Package, Scale, ShieldAlert, type LucideIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CHECKS } from "@/lib/checks"

/**
 * The 6 SQG checks as an orbiting constellation (adapted from the Radial Orbital
 * Timeline snippet). A node "fires" when its rule has findings (warm glow);
 * clean checks stay cool. Click a node to read what it detects + sibling checks.
 * Auto-rotation pauses under reduced-motion (nodes fall into a static ring).
 */

interface Node {
  id: string
  title: string
  count: number
  blurb: string
  icon: LucideIcon
  related: string[]
  fired: boolean
  energy: number
}

const ICONS: Record<string, LucideIcon> = {
  SQG001: Package,
  SQG002: KeyRound,
  SQG003: FileCode2,
  SQG004: ShieldAlert,
  SQG005: Scale,
  SQG006: Bug,
}
// Sibling groups (same risk family) — drives the "connected checks" links.
const GROUPS: string[][] = [
  ["SQG001", "SQG004", "SQG005"], // supply chain
  ["SQG002"], // secrets
  ["SQG003", "SQG006"], // code quality / safety
]
const RULES = ["SQG001", "SQG002", "SQG003", "SQG004", "SQG005", "SQG006"]

function relatedOf(id: string): string[] {
  const g = GROUPS.find((grp) => grp.includes(id)) ?? []
  return g.filter((x) => x !== id)
}

export function RadialOrbital({ byRule }: { byRule: Record<string, number> }) {
  const max = Math.max(1, ...RULES.map((id) => byRule[id] ?? 0))
  const nodes: Node[] = RULES.map((id) => {
    const count = byRule[id] ?? 0
    return {
      id,
      title: CHECKS[id]?.name ?? id,
      count,
      blurb: CHECKS[id]?.blurb ?? "",
      icon: ICONS[id],
      related: relatedOf(id),
      fired: count > 0,
      energy: count === 0 ? 8 : Math.round((count / max) * 100),
    }
  })

  const prefersReduced =
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

  const [rotation, setRotation] = useState(0)
  const [autoRotate, setAutoRotate] = useState(!prefersReduced)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [radius, setRadius] = useState(180)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!autoRotate) return
    const t = setInterval(() => setRotation((r) => (r + 0.3) % 360), 50)
    return () => clearInterval(t)
  }, [autoRotate])

  // Shrink the orbit so nodes + labels never clip on narrow (mobile) screens.
  useEffect(() => {
    const measure = () => {
      const w = containerRef.current?.clientWidth ?? 360
      setRadius(Math.max(96, Math.min(180, Math.floor(w / 2 - 72))))
    }
    measure()
    window.addEventListener("resize", measure)
    return () => window.removeEventListener("resize", measure)
  }, [])

  const toggle = (id: string) => {
    setActiveId((cur) => {
      const next = cur === id ? null : id
      setAutoRotate(next === null ? !prefersReduced : false)
      return next
    })
  }

  const pos = (index: number) => {
    const angle = ((index / nodes.length) * 360 + rotation) % 360
    const rad = (angle * Math.PI) / 180
    return {
      x: radius * Math.cos(rad),
      y: radius * Math.sin(rad),
      z: Math.round(100 + 40 * Math.cos(rad)),
      opacity: Math.max(0.5, Math.min(1, 0.5 + 0.5 * ((1 + Math.sin(rad)) / 2))),
    }
  }

  const active = nodes.find((n) => n.id === activeId) ?? null

  return (
    <div
      ref={containerRef}
      onClick={(e) => {
        if (e.target === containerRef.current) {
          setActiveId(null)
          setAutoRotate(!prefersReduced)
        }
      }}
      className="relative flex h-[560px] w-full items-center justify-center overflow-hidden rounded-lg"
    >
      {/* Core */}
      <div className="absolute z-10 flex h-16 w-16 items-center justify-center">
        <div className="absolute h-16 w-16 rounded-full bg-brand-gradient opacity-80 blur-[2px]" />
        <div className="absolute h-24 w-24 animate-orbit-pulse rounded-full border border-brand-teal/30" />
        <div className="absolute h-10 w-10 rounded-full bg-bg/80 backdrop-blur" />
        <span className="relative font-display text-xs font-bold text-text">SQG</span>
      </div>

      {/* Orbit ring */}
      <div
        className="absolute rounded-full border border-border"
        style={{ height: radius * 2, width: radius * 2 }}
      />

      {/* Nodes */}
      {nodes.map((n, i) => {
        const p = pos(i)
        const isActive = activeId === n.id
        const Icon = n.icon
        const tone = n.fired ? "sev-high" : "brand-teal"
        return (
          <div
            key={n.id}
            className="absolute transition-all duration-700"
            style={{
              transform: `translate(${p.x}px, ${p.y}px)`,
              zIndex: isActive ? 200 : p.z,
              opacity: isActive ? 1 : p.opacity,
            }}
          >
            <button
              onClick={(e) => {
                e.stopPropagation()
                toggle(n.id)
              }}
              aria-label={`${n.title}: ${n.count} findings`}
              className={`relative flex h-12 w-12 items-center justify-center rounded-full border-2 transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo ${
                isActive ? "scale-125" : "hover:scale-110"
              } ${
                n.fired
                  ? "border-sev-high bg-sev-high/15 text-sev-high"
                  : "border-brand-teal/50 bg-surface text-brand-teal"
              }`}
              style={n.fired ? { boxShadow: `0 0 ${6 + n.energy / 6}px var(--sev-high)` } : undefined}
            >
              <Icon className="h-5 w-5" aria-hidden />
              {n.count > 0 && (
                <span className="tnum absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-sev-certain px-1 text-[10px] font-bold text-bg">
                  {n.count}
                </span>
              )}
            </button>
            <div
              className={`pointer-events-none absolute left-1/2 top-14 -translate-x-1/2 whitespace-nowrap text-xs font-medium tracking-wide transition-all ${
                isActive ? "text-text" : "text-text-muted"
              }`}
            >
              {n.title}
            </div>
          </div>
        )
      })}

      {/* Active detail card (fixed, not orbiting — readable) */}
      {active && (
        <Card className="absolute bottom-4 left-1/2 z-[300] w-72 -translate-x-1/2 animate-dot-reveal">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <Badge variant={active.fired ? "alert" : "clean"}>
                {active.fired ? `${active.count} found` : "Clean"}
              </Badge>
              <span className="font-mono text-xs text-text-faint">{active.id}</span>
            </div>
            <CardTitle className="mt-2 text-sm">{active.title}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-text-muted">
            <p>{active.blurb}</p>
            <div className="mt-3 border-t border-border pt-3">
              <div className="mb-1 flex items-center justify-between">
                <span>Activity</span>
                <span className="tnum">{active.energy}%</span>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-surface-elevated">
                <div className="h-full bg-brand-gradient" style={{ width: `${active.energy}%` }} />
              </div>
            </div>
            {active.related.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border pt-3">
                {active.related.map((rid) => (
                  <button
                    key={rid}
                    onClick={(e) => {
                      e.stopPropagation()
                      toggle(rid)
                    }}
                    className="rounded-md border border-border px-2 py-0.5 text-xs text-text-muted transition-colors hover:bg-surface-elevated hover:text-text"
                  >
                    {CHECKS[rid]?.name ?? rid}
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
