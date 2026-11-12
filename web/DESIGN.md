---
name: Command Wall
description: Design system for AI Slop Quarantine Guard — black-starfield operator cockpit. Single source of truth; token values mirror the CSS vars defined in web/app/dashboard/wall.css (:root block) and named by tailwind.config.ts. Supersedes "Aurora on Black".
colors:
  surfaces:
    bg: "#04060C"
    bg-deep: "#02030A"
    bg-glow: "#0A1024"
    surface: "#0A0E18"
    surface-translucent: "rgba(12,17,28,0.55)"
    line: "rgba(120,160,255,0.10)"
    line-strong: "rgba(120,160,255,0.20)"
  brand:
    accent-cyan: "#16E0E0"
    accent-magenta: "#FF3D8B"
    accent-violet: "#8B5CF6"
    accent-green: "#2DE08A"
    brand-gradient: "linear-gradient(110deg, #FF3D8B 0%, #8B5CF6 50%, #16E0E0 100%)"
  action:
    act-queued: "#FF3D8B"
    act-running: "#16E0E0"
    act-completed: "#2DE08A"
    act-failed: "#FF3B5C"
  severity:
    sev-certain: "#FF3B5C"
    sev-high: "#FF8A3D"
    sev-medium: "#FFC83D"
    sev-clean: "#2DE08A"
  text:
    text: "#EAF0FF"
    text-muted: "#8A95AD"
    text-faint: "#6F7890"
    on-accent: "#04060C"
typography:
  display: "Space Grotesk"
  body: "Inter"
  mono: "JetBrains Mono"
  floor-px: 12
  scale-px: [12, 13, 14, 16, 18, 20, 24, 32]
  figures: "clamp() utilities — hero 52–76px, tile 32–48px; tabular-nums mandatory on every number"
rounded:
  xs: 4
  sm: 6
  md: 8
  lg: 12
  xl: 16
  full: 9999
spacing:
  scale-px: [4, 8, 12, 16, 24, 32, 48, 64]
motion:
  micro-ms: 150
  base-ms: 200
  enter-ms: 300
  exit: "65% of the enter duration"
  easing-enter: "cubic-bezier(0.22, 1, 0.36, 1)"
  easing-exit: "cubic-bezier(0.55, 0, 1, 0.45)"
  stagger-ms: 40
  count-up-ms: 600
  signature: "scan-complete beam sweep — 700ms, once per completed scan"
components:
  wall-panel: "transparent, card-less region floating on the starfield (the wall's signature)"
  wall-card: "solid surface #0A0E18 + 1px line-strong + elev-1 shadow, radius lg"
  wall-chip: "icon + text + color pill, 12px, tinted background 12% of its color"
  wall-focus: "2px solid accent-cyan ring (box-shadow), on every interactive element, never removed"
---

# Command Wall

The design system of AI Slop Quarantine Guard. One black starfield, one token set,
two color ramps that never mix. Everything on screen is either **identity** (neon),
**risk** (warm severity), or **structure** (surfaces/text). If a pixel cannot say
which of the three it is, it does not ship.

This file supersedes **"Aurora on Black"**. The old system's surface, text, and
accent values are retired; the warm severity values survive unchanged. The exact
old-name → new-name migration map lives in `docs/design/dashboard-overhaul.md` §1.

## Where tokens live

Token VALUES are defined once, as CSS custom properties, in the `:root` block of
`web/app/dashboard/wall.css` (imported globally by `AppShell`, so they reach every
route including `/login`). `web/app/globals.css` keeps only base element styles
(body font, headings, reduced-motion kill switch). `tailwind.config.ts` names the
vars (`bg-bg`, `text-text`, `border-line`, `text-sev-certain`, …). Edit the CSS
var, never a scattered hex. This file is the human-readable mirror.

## Two ramps, never mixed

- **Neon brand (cool):** cyan `#16E0E0` · magenta `#FF3D8B` · violet `#8B5CF6` ·
  green `#2DE08A`. Means identity, liveness, and health: brand marks, live pulse,
  "online", orbit decorations, the CTA gradient.
- **Warm severity:** crimson `#FF3B5C` · amber `#FF8A3D` · gold `#FFC83D` ·
  emerald `#2DE08A`. Means **findings** — a warm pixel always traces to a real
  finding count. Never used for decoration, hover states, or brand moments.
- Overlap note: `sev-clean` and `accent-green` share the value `#2DE08A`
  deliberately ("clean" and "healthy" are the same fact), but the two token names
  stay separate so intent stays greppable. `act-failed` shares the crimson value
  because a failed scan is a genuine risk state.
- **Severity is never color-only.** Every severity signal ships as icon + text
  label + color. Icons: ShieldAlert (certain) · AlertTriangle (high) · Info
  (medium) · ShieldCheck (clean) — from `lib/severity.ts`, lucide only.

## Typography

- **Display** Space Grotesk 600/700 — section labels and the brand wordmark only.
- **Body/UI** Inter 400/500/600 — everything else.
- **Mono** JetBrains Mono — code, refs, SHAs, timestamps, log lines, tabular figures.
- Loaded once via `next/font/google` as `--font-display` / `--font-sans` / `--font-mono`.

**Scale (12px absolute floor — nothing renders smaller, ever):**

| Token | px | Use |
|---|---|---|
| `text-xs` | 12 | section labels, badges, chips, mono meta, timestamps, axis ticks |
| `text-sm` | 13 | nav, filter chips, sub-lines, secondary body |
| `text-base` | 14 | body, list rows, inputs |
| `text-md` | 16 | text inputs (prevents iOS zoom), emphasized body |
| `text-lg` | 18 | panel titles |
| `text-xl` | 20 | major panel titles |
| `text-2xl` | 24 | page-level headings |
| `text-3xl` | 32 | rare emphasis headings |

Figures are clamp() utilities, not scale steps: `.wall-figure-hero`
(clamp(3.25rem, 5.5vw, 4.75rem)) for the cockpit hero, `.wall-figure-tile`
(clamp(2rem, 3.5vw, 3rem)) for tile leads. Line-height: labels 1.2, body 1.5,
mono 1.5, figures 0.92.

**Tracked-caps rule:** `letter-spacing ≥ 0.05em` + uppercase is allowed in exactly
two places — `.wall-label` section labels, and the brand wordmark in the dock/boot.
Buttons, nav items, toasts, badges, chips, and table headers render in normal case.

**Tabular figures everywhere.** Every number, count, percentage, timestamp, and
duration uses `font-variant-numeric: tabular-nums` (`.wall-num` / `.tnum`) so
polling updates never shift layout.

## Spacing, radius, elevation

- **Spacing:** 4/8 rhythm — 4, 8, 12, 16, 24, 32, 48, 64. Page gutter 12px; tile
  padding 16px vertical / 20px horizontal; related-element gap 8–12px; section gap 24–32px.
- **Radius (one scale):** `xs` 4 (heat cells, dots) · `sm` 6 (chips, badges,
  tooltips) · `md` 8 (buttons, inputs, tabs, list rows) · `lg` 12 (panels, cards) ·
  `xl` 16 (modals, palette) · `full` (dots, pills, progress bars).
- **Elevation rule (one system):** the wall's regions are **transparent and
  card-less** — content floats on the starfield. Only *floating* surfaces get a
  body: `surface` solid + 1px `line-strong` border + `elev-1`
  (`0 8px 40px -12px rgba(0,0,0,0.6)`); modal-level adds `elev-2`
  (`0 30px 100px -20px rgba(0,0,0,0.8)`) over a scrim `rgba(2,4,10,0.6)` with 6px blur.
  `backdrop-filter` blur is allowed only on the modal scrim and toasts — never as
  panel decoration.
- **Borders:** decorative hairlines = `line`; interactive boundaries (inputs, tabs) =
  `line-strong`; state edges (focus, active) = accent cyan. `line` and `line-strong`
  are decorative-only (they do not reach 3:1) — any border that is the *only*
  visual identifier of a control must pair with a fill, a label, or the focus ring.

## Motion

- Durations: 150ms (hover/press/state), 200ms (chips/tabs/filter swaps, crossfades),
  300ms (entrances, overlay open). Exits run at ~65% of their enter duration
  (100/130/200ms tokens).
- Easing: `cubic-bezier(0.22,1,0.36,1)` entering, `cubic-bezier(0.55,0,1,0.45)`
  exiting, ease-in-out for the sweep. Never linear for UI transitions.
- List/grid entrances stagger **40ms** per item, capped at 8 items — the rest of
  the list appears with the 8th. Animate transform/opacity only.
- **Count-ups:** 600ms ease-out on the cockpit hero and tile lead figures, on mount
  and on value change. Tabular figures prevent width shift.
- **ONE signature moment — the scan-complete beam sweep:** when a scan newly
  completes, a 2px cyan light bar (gradient edge fade + soft glow) sweeps top→bottom
  across the whole wall once, 700ms ease-in-out, then unmounts. One pass per
  completion; queued events coalesce to one sweep. Skipped entirely under
  reduced motion. It is the only "spectacle" animation in the app; the globe's
  beam pulses and spin are ambient continuity, not spectacle.
- **`prefers-reduced-motion`** collapses all animation (global kill switch in
  `globals.css`), plus explicit degenerate modes: globe renders its static frame,
  count-ups render instantly, the sweep does not mount, entrances render final state.

## Accessibility (floor, non-negotiable)

- Body text ≥ 4.5:1 on `bg`; large text (≥24px normal / ≥18.66px bold) ≥ 3:1;
  secondary text ≥ 4.5:1 (the old 3:1 secondary allowance is retired — muted
  #8A95AD ≈ 6.7:1, faint #6F7890 ≈ 4.6:1 on #04060C).
- Severity/data colors ≥ 3:1 against `bg` for non-text signals; all five pass
  (crimson 5.8:1, amber 8.6:1, gold 13.1:1, green 12.1:1, cyan 12.3:1).
- **Focus rings:** 2px solid `accent-cyan` via `.wall-focus` on every interactive
  element. Never removed, never replaced by color-only state.
- **Touch targets ≥ 44×44px** (Apple HIG) at every breakpoint. Where a compact
  visual is needed (filter chips), the visual is ≥32px and a pseudo-element
  extends the hit area to 44px on `pointer: coarse`.
- Keyboard: full tab order matching visual order; palette and modals trap focus
  and provide Escape; charts/orbits expose keyboard-reachable equivalents.
- Charts and the globe carry a text alternative (visually-hidden summary or a real
  HTML twin — Recent Scans is the globe's accessible twin). Screen-reader text is
  never the color channel alone.
- `aria-live="polite"` for status toasts, `role="alert"` for the API error banner.
- No emoji icons anywhere; lucide only, one stroke family, 14/16/20px sizes.

## Components (wall.css utility contract)

| Utility | Definition |
|---|---|
| `.wall-root` | page backdrop: `#04060C`→`#02030A` radial + top `#0A1024` glow + tiled starfield ::before; `isolation: isolate` |
| `.wall-panel` | transparent region (no fill, border, or blur) |
| `.wall-card` | floating surface: solid `surface`, 1px `line-strong`, radius `lg`, `elev-1` |
| `.wall-label` | section label: display font, 12px, 500, uppercase, 0.06em tracking, `text-muted` — the ONLY tracked-caps text |
| `.wall-sub` | 13px secondary line, `text-muted`, line-height 1.5 |
| `.wall-mono` | mono, 12px minimum, line-height 1.5, tabular |
| `.wall-num` | tabular-nums, 700, -0.01em |
| `.wall-figure-hero` / `.wall-figure-tile` | thin (200) tabular figures, line-height 0.92 |
| `.wall-chip` | severity/summary pill: icon 14px + 12px 500 text, tinted bg (color at 12%), radius `sm`, 28px tall |
| `.wall-chip-sm` | 24px row-scale variant for FixFirst/Recent rows |
| `.wall-filter` | stream filter chip: 32px visual, ≥44px hit, radius `sm`, 12px text |
| `.wall-tab` | source/tab button: 44px min-height, radius `md`, 13px text |
| `.wall-cta` / `.wall-cta-secondary` | primary gradient / outlined secondary, 44–46px, radius `md`, `on-accent` text on gradient |
| `.wall-input` | 44px min-height, 16px text, radius `md`, `line-strong` border, cyan focus |
| `.wall-focus` | 2px cyan focus ring (box-shadow), radius `md` |
| `.wall-sweep` | the signature beam (see Motion) |
| `.wall-skeleton` | opacity-shimmer placeholder block, 1.2s loop; mounted only after a 300ms load delay |
| `.wall-empty` | empty-state block: icon 20px + 13px copy + optional 13px cyan CTA link |
| `.wall-tooltip` | globe hover tooltip: solid `surface`, radius `sm`, 12px, `elev-1` |
| `.wall-divider` | 1px `line` hairline |
| `.wall-hairline` | 2px neon gradient top bar (brand moment, dock only) |
| `.wall-scroll` | 6px slim scrollbar tinted `line-strong` |
| `.wall-glow-cyan` / `.wall-glow-magenta` | text glow — hero figure and brand wordmark only |

## Do / Don't

- **Do** keep panels transparent on the starfield; reserve solid surfaces for
  things that truly float (palette, toasts, overlay cards).
- **Do** use the gradient sparingly — CTA, brand mark, dock hairline. Identity moments.
- **Do** map every pixel to a real API field (`web/lib/types.ts`). An invented
  number is a lie, not a design choice.
- **Don't** put warm severity colors on brand elements or neon accents on findings.
- **Don't** ship a state that is color-only; don't render text below 12px; don't
  track-caps anything that is not a section label or the wordmark.
- **Don't** add a second "hero" number anywhere while the cockpit hero exists.
