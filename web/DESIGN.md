---
name: Aurora on Black
description: Design system for the AI Slop Quarantine Guard dashboard — black, futuristic, minimalist analytics. Source of truth for tokens; mirrors app/globals.css + tailwind.config.ts.
colors:
  surfaces:
    bg: "#06080A"
    surface: "#0E1116"
    surface-elevated: "#141922"
    border: "rgba(120,140,255,0.12)"
    border-strong: "rgba(120,140,255,0.22)"
  brand:
    brand-indigo: "#4A5BFF"
    brand-teal: "#16C8D4"
    brand-emerald: "#2DE08A"
    brand-gradient: "linear-gradient(120deg, #4A5BFF 0%, #16C8D4 52%, #2DE08A 100%)"
    scan: "#22D3EE"
  severity:
    sev-certain: "#FF3B5C"
    sev-high: "#FF8A3D"
    sev-medium: "#FFC83D"
    sev-clean: "#2DE08A"
  text:
    text: "#EAEEF6"
    text-muted: "#9AA4B2"
    text-faint: "#5B6472"
typography:
  display: "Space Grotesk"
  body: "Inter"
  mono: "JetBrains Mono"
  scale: [12, 14, 16, 20, 28, 40, 56]
rounded:
  sm: 10
  md: 16
  lg: 22
spacing: [4, 8, 12, 16, 24, 32, 48, 64]
components:
  glass: "rgba(18,22,30,0.6) + backdrop-blur(18px) saturate(140%) + 1px aurora border + inner top-highlight"
---

# Aurora on Black

The dashboard is a **black, futuristic, minimalist** analytics surface. Two color axes,
never mixed:

- **Brand (cool aurora):** indigo → teal → emerald. Identity, gradients, active state, the live `scan` pulse.
- **Severity (warm):** crimson → amber → gold → emerald. Findings only. A warm dot means "a thing was found."

## Why two axes
Brand and severity must never be confused. A user glancing at the screen reads warmth as
risk and cool as identity/health. Keeping them on separate ramps is what lets the product
say things honestly at a glance — consistent with the "never lie about a fact" promise.

## Tokens
Values live once as CSS custom properties in `app/globals.css` `:root`, named by Tailwind in
`tailwind.config.ts` (`bg-bg`, `text-text-muted`, `border-border`, `bg-sev-certain`, …). Edit the
CSS var, not scattered hex. This file is the human-readable mirror.

## Typography
- **Display** Space Grotesk 600/700 — bold uppercase headers.
- **Body/UI** Inter 400/500/600.
- **Mono** JetBrains Mono — code evidence, SHAs, `file:line`, line numbers, tabular figures (`.tnum`).
- Loaded via `next/font/google` as `--font-display` / `--font-sans` / `--font-mono`.

## Effects
- **Glass** (`.glass`): translucent panel + 18px blur + 1px aurora border + inner top highlight.
- **Glow** (`shadow-glow`): low-opacity aurora radial behind hero / active elements.
- **AuroraBackdrop**: fixed, drifting radial blobs behind the whole app (pure CSS, no WebGL).

## Motion
Framer Motion (added when interactive surfaces land). Micro 150–220ms ease-out; card entrance
stagger 40ms; count-up numbers; `scan-pulse` shimmer on in-progress rows; spring hover lift.
**`prefers-reduced-motion` is honored globally in `globals.css`** — all animation collapses to instant.

## Accessibility (floor, non-negotiable)
- Text ≥4.5:1 on `--bg`; secondary ≥3:1. Visible hairline borders.
- **Severity is never color-only** — always icon + text + color.
- Focus rings (brand-indigo), keyboard nav, ≥44px touch targets.
- Charts get a text-summary / data-table fallback (added with the charts).

## Do / Don't
- **Do** layer surfaces (bg → surface → surface-elevated) for depth; use the gradient sparingly (identity moments).
- **Don't** use brand colors for severity or vice-versa; don't put findings on the cool ramp; don't ship color-only state.

## 3D (deferred to Stage 4+)
WebGL "trust core" hero (`@react-three/fiber` + `drei`) on `/dashboard` only — capped DPR, paused
offscreen, static fallback for reduced-motion / no-WebGL. CSS/Framer faux-3D elsewhere. Not part of
the Stage 3 foundation (keeps the install lean).
