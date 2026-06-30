# AI Slop Quarantine Guard — Dashboard: Design System + 4-Page Build

> Durable copy of the approved plan (saved into the repo before /compact). Mirror of the
> plan-mode plan file. Resume from here.

## Context

The project is a GitHub App that scans every pull request for "AI slop" — hallucinated packages,
leaked secrets, CVEs, risky licenses, SAST issues, placeholder code, and committed AI scratchpads
(checks `SQG001`–`SQG007`). Backend is FastAPI + Postgres + arq. The `web/` frontend is a bare
Next.js 15 shell — `app/page.tsx` is a 6-line placeholder, Tailwind is configured but **not even
installed**, no components, no design tokens, no `globals.css`. Clean slate.

Goal: build a **black, futuristic, minimalist analytics dashboard** that fuses the best of four
reference dashboards, plus a **reusable `DESIGN.md`** (Google `design.md` format) so the design
system is captured once and re-read by agents across sessions.

**Locked decisions (from user):**
1. **Brand name on UI:** "AI Slop Quarantine Guard" (codename). *Note: PRD line 4 marks this codename
   as pejorative/internal-only and mandates a neutral customer-facing name ("PR Quality & Security
   Gate"). User chose the codename anyway — deliberate override. Swappable via one token (`name`) +
   one wordmark component.*
2. **Scope:** Full 4-page app — Overview, Analyses list, Analysis detail, Settings — mock data.
3. **3D:** Both — real WebGL hero (react-three-fiber) **and** CSS/Framer depth on cards.
4. **Gradient:** **Aurora** — cool indigo→teal→emerald brand; severity is a separate warm ramp.

---

## Design System — "Aurora on Black"

### Color tokens

**Surfaces (cool near-black, layered):**
| Token | Value | Use |
|---|---|---|
| `bg` | `#06080A` | app background |
| `surface` | `#0E1116` | cards, panels |
| `surface-elevated` | `#141922` | popovers, hovered cards, modals |
| `border` | `rgba(120,140,255,0.12)` | hairline glass borders |
| `border-strong` | `rgba(120,140,255,0.22)` | focus / active edges |

**Brand — Aurora gradient:**
| Token | Value |
|---|---|
| `brand-indigo` | `#4A5BFF` |
| `brand-teal` | `#16C8D4` |
| `brand-emerald` | `#2DE08A` |
| `brand-gradient` | `linear-gradient(120deg, #4A5BFF 0%, #16C8D4 52%, #2DE08A 100%)` |
| `scan` | `#22D3EE` (live/in-progress pulse, scan-beam) |

**Severity ramp (separate WARM axis):**
| Token | Value | Maps to |
|---|---|---|
| `sev-certain` | `#FF3B5C` crimson | CERTAIN / block-eligible (SQG001, SQG002) |
| `sev-high` | `#FF8A3D` amber | HIGH (SQG004/005/006) |
| `sev-medium` | `#FFC83D` gold | MEDIUM (SQG003/007) |
| `sev-clean` | `#2DE08A` emerald | clean pass |

**Text:** `text` `#EAEEF6` · `text-muted` `#9AA4B2` · `text-faint` `#5B6472` (all ≥4.5:1).

### Typography
- **Display:** `Space Grotesk` 600/700 (bold uppercase headers).
- **Body/UI:** `Inter` 400/500/600.
- **Mono:** `JetBrains Mono` (code evidence, SHAs, line numbers, tabular numbers).
- Via `next/font/google`. Scale 12/14/16/20/28/40/56. Body 16, line-height 1.5. Tabular figures for data.

### Radius / spacing / effects
- Radius: `sm` 10 · `md` 16 · `lg` 22 · `full`. Cards default `lg`.
- Spacing 4/8 rhythm (4 8 12 16 24 32 48 64).
- **Glass:** `rgba(18,22,30,0.6)` + `backdrop-filter: blur(18px) saturate(140%)` + 1px aurora border + inner top-highlight.
- **Glow:** low-opacity aurora radial glows behind hero/active cards.

### Motion (Framer Motion; honor `prefers-reduced-motion`)
- Micro 150–220ms ease-out; card entrance stagger 40ms; count-up numbers on mount.
- Live polling → `scan` shimmer on `in_progress` rows. Spring hover lift (scale 1.02, y -2). Exit ~65% of enter.
- Reduced-motion → instant opacity; 3D renders static frame.

### 3D (both modes)
- **WebGL hero** (`@react-three/fiber` + `drei`): rotating translucent icosahedron "trust core",
  wireframe shell, emissive scan-ring sweep, inward-drifting particles (PRs). Aurora material,
  capped DPR, paused offscreen, static fallback for reduced-motion / no-WebGL.
- **CSS/Framer faux-3D** elsewhere: perspective tilt on hover, parallax glow, stacked translucent planes. No three.js on non-hero routes.

---

## Deliverable 1 — `web/DESIGN.md` (Google `design.md` format)
YAML frontmatter (tokens under `colors/typography/rounded/spacing/components`) + markdown body
(rationale, motion, chart system, do/don't). Close the loop with the installed CLI:
- `designmd lint web/DESIGN.md` → must pass (structure + WCAG contrast).
- `designmd export css-tailwind web/DESIGN.md` → Tailwind `@theme` CSS → source of truth for the
  Tailwind theme + `globals.css` variables (no drift).

---

## Deliverable 2 — 4-page dashboard

### Stack additions (install in `web/`)
- `tailwindcss postcss autoprefixer` (NOT installed yet) + `globals.css` + PostCSS.
- `shadcn/ui` init → add: card badge button table tabs dialog input label switch select textarea skeleton separator tooltip dropdown-menu sonner.
- `lucide-react`, `framer-motion`, `three @react-three/fiber @react-three/drei`, `recharts`.
- Custom SVG + Framer for signature visuals (radial gauge, dot-density, gantt timeline).

### File structure (`web/`)
```
app/
  globals.css                 # token CSS vars (from DESIGN.md) + base
  layout.tsx                  # fonts, Sidebar, AuroraBackdrop, Toaster
  page.tsx                    # redirect → /dashboard
  dashboard/page.tsx          # Overview (showcase)
  analyses/page.tsx           # Analyses list
  analyses/[id]/page.tsx      # Analysis detail
  settings/page.tsx           # Settings
components/
  ui/                         # shadcn
  three/TrustCore.tsx         # R3F hero (dynamic import ssr:false)
  layout/{Sidebar,Topbar,AuroraBackdrop}.tsx
  charts/{RadialGauge,AreaTrend,DotDensity,SeverityBars,PipelineTimeline}.tsx
  dashboard/{KpiCard,GradientCta}.tsx
  findings/{FindingCard,SeverityBadge,StatusBadge}.tsx
  settings/SettingsForm.tsx
lib/
  types.ts                    # Installation, AnalysisSummary, AnalysisDetail, Finding, Evidence,
                              #   RepoSettings, Confidence, AnalysisStatus, TrustStatus, RuleId
  mock-data.ts                # fixtures (SQG001–007 findings, evidence, timings, cost)
  checks.ts                   # SQG catalog metadata
  format.ts                   # number/duration/cost/relative-time formatters
  api.ts                      # typed fetch wrappers behind USE_MOCK_DATA flag
```
Types from `docs/DATA_MODEL.md` + `docs/API_SPEC.md` (real fields: `confidence`, `block_eligible`,
`trust_status`, `duration_ms`, `cost_usd`, `evidence.{snippet,context_before,context_after}`).

### Pages
1. **/dashboard** — Topbar (wordmark + pill nav + search + account). Hero: TrustCore (WebGL) +
   RadialGauge "Clean Pass Rate %" + 3 KPI cards (PRs analyzed / CERTAIN blocked / p95 time, count-up,
   hover-tilt). Row2: AreaTrend (findings 30d, aurora fill + dashed forecast) + SeverityBars (by SQG).
   Row3: PipelineTimeline (recent runs gantt, scan-pulse on in_progress) + GradientCta ("Connect a
   repository"). Trust-status strip (completed/degraded/failed) = PRD "never lie / fail-safe" promise.
2. **/analyses** — filterable paginated table: repo · PR# · title · status · severity counts (mini
   dot-density) · duration · cost · time. Row→detail. 5s polling shimmer on in_progress. Empty + skeletons.
3. **/analyses/[id]** — PR header (repo, PR#, head SHA mono, refs, status, duration, cost). Findings
   grouped CERTAIN→HIGH→MEDIUM via FindingCard (rule badge, file:line mono, message, collapsible
   evidence snippet w/ offending line crimson, fix_suggestion callout). Clean → emerald all-clear + TrustCore at rest.
4. **/settings** — SettingsForm: block_mode switch (+Phase-9 note), blocked_rules multiselect
   (SQG001/002), ai_enabled + ai_model select, path/rule allowlist textareas, retain_findings_days
   select. Optimistic save → sonner toast. Destructive emphasized + separated.

### A11y / quality floor
Dark contrast text ≥4.5:1 / secondary ≥3:1, visible borders. Severity never color-only (icon+text).
Focus rings, keyboard nav, chart text-summary/data-table fallback + tooltips on hover & focus.
Touch targets ≥44px. `prefers-reduced-motion` fully honored.

---

## Verification
1. `cd web && npm install && npm run dev` → boots :3000, no console errors.
2. All 4 routes render w/ mock data; nav between them; back preserves state.
3. `designmd lint web/DESIGN.md` passes.
4. `designmd export css-tailwind web/DESIGN.md` → tokens match `globals.css`.
5. `npm run build` clean (3D dynamically imported ssr:false).
6. Reduced-motion → graceful degrade; 375px width → no horizontal scroll.
7. Visual QA vs 4 refs: black+glass (Stakent), uppercase+pill nav (CheckBox), icon rail (nixtio), radial hero + soft cards (Financial) — unified under Aurora.

## Out of scope (this pass)
Real FastAPI dashboard routes, Supabase auth/OAuth, AI Crew explain tab (Phase 7), finding bypass
(Phase 9). Mock data behind `USE_MOCK_DATA`; swap to live API = one-file change in `lib/api.ts`.
