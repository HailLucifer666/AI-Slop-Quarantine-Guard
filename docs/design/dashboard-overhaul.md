# dashboard-overhaul — Command Wall component specs (Wave 2 build spec)

> Wave 1 output of `feat/dashboard-overhaul`. Binding on team-frontend A (cockpit)
> and B (system + cleanup). Values are exact; nothing here is "choose later".
> Design system source of truth: `web/DESIGN.md` (Command Wall). Plan of record:
> `docs/plan-dashboard-overhaul.md`. Data truth: `web/lib/types.ts` — every number
> on screen traces to a real field; nothing is fabricated.
>
> Priority ladder for review (ui-ux-pro-max): accessibility → touch → performance →
> style → layout → type/color → animation → forms → nav → charts.

---

## 0. Ownership of this spec

| Contract | Owner file | Landed by |
|---|---|---|
| Merged token values (`:root`) + all `.wall-*` utilities | `web/app/dashboard/wall.css` | **frontend-A** (one pass, §10) |
| Base element styles, reduced-motion kill switch, Tailwind theme names | `web/app/globals.css`, `web/tailwind.config.ts` | **frontend-B** (§11) |
| Cockpit panels, globe, FixFirst, `useWallData`/`types.ts` extensions | files per plan §file-ownership | **frontend-A** |
| Chrome (dock, palette, boot, login, effects, findings, scan/analyses/checks/settings pages) | files per plan §file-ownership | **frontend-B** |

B consumes wall.css; B never edits it. If B needs a utility that is missing, B
reports the need to the orchestrator (relay to A).

---

## 1. Migration map — the two old token systems become one

Wave 1 found these live, competing systems (Wave 2 must eliminate all but the first):

1. **Aurora** (`globals.css :root` + tailwind names): `--bg #06080A`, `--text
   #EAEEF6`, `--text-faint #5B6472` (≈3.2:1 on its own bg — failed AA on 10–11px
   text), `--brand-indigo/-teal/-emerald`, `--scan #22D3EE`, `--border`,
   `--glass-bg`/`.glass`, `--brand-gradient` (indigo→teal→emerald).
2. **Wall** (`wall.css .wall-root/.wall-vars`): `--wall-bg #04060C`, `--wall-text
   #EAF0FF`, `--wall-faint #525B71` (≈3.0:1 — failed AA), `--wall-cyan/-magenta/
   -violet/-green`, `--wall-line`, `--wall-sev-*` (duplicate of globals severity).
3. **GlobeCore local hexes** (a third near-duplicate set): `#22e8e8`, `#6a5cf2`,
   `#2b86ff`, `#ff3d8b`, `#22e8e8` again — drift already visible (`#22e8e8` vs the
   token `#16e0e0`; `#6a5cf2` vs token `#8b5cf6`).
4. **BootScreen hardcoded radial** (`#05070f/#02030a/#000000`) — a fourth bg.

### 1a. CSS var rename map (mechanical, both A and B apply to the files they own)

| Old | New | Value (final) |
|---|---|---|
| `--wall-bg` / `--bg` (Aurora) | `--bg` | `#04060C` |
| `--wall-bg-deep` | `--bg-deep` | `#02030A` |
| *(none — BootScreen hardcode)* | `--bg-glow` | `#0A1024` |
| `--wall-panel-solid` | `--surface` | `#0A0E18` |
| `--wall-panel` | `--surface-translucent` | `rgba(12,17,28,0.55)` |
| `--wall-line` / `--border` | `--line` | `rgba(120,160,255,0.10)` |
| `--wall-line-strong` / `--border-strong` | `--line-strong` | `rgba(120,160,255,0.20)` |
| `--wall-cyan` / `--scan` | `--accent-cyan` | `#16E0E0` |
| `--wall-magenta` | `--accent-magenta` | `#FF3D8B` |
| `--wall-violet` | `--accent-violet` | `#8B5CF6` |
| `--wall-green` / `--brand-emerald` | `--accent-green` | `#2DE08A` |
| `--brand-indigo` | *(retired — focus rings become cyan, gradient merged)* | — |
| `--brand-teal` | *(retired — MiniSparkline default becomes `--accent-cyan`)* | — |
| `--wall-act-*` | `--act-queued #FF3D8B`, `--act-running #16E0E0`, `--act-completed #2DE08A`, `--act-failed #FF3B5C` | unchanged values |
| `--wall-sev-*` / `--sev-*` | `--sev-certain #FF3B5C`, `--sev-high #FF8A3D`, `--sev-medium #FFC83D`, `--sev-clean #2DE08A` | unchanged values |
| `--wall-text` / `--text` | `--text` | `#EAF0FF` |
| `--wall-muted` / `--text-muted` | `--text-muted` | `#8A95AD` |
| `--wall-faint` / `--text-faint` | `--text-faint` | **`#6F7890`** (lifted from #525B71/#5B6472: was ≈3:1, now ≈4.6:1 — fixes the AA failure on 10–11px meta text) |
| *(none)* | `--on-accent` | `#04060C` (text on gradient/neon fills) |
| `--brand-gradient` | `--brand-gradient` | `linear-gradient(110deg, #FF3D8B 0%, #8B5CF6 50%, #16E0E0 100%)` (wall wins; Aurora gradient retired) |
| `--glass-bg` + `.glass` | *(retired — floating surfaces use `.wall-card`)* | — |
| `--shadow-glass` / `--shadow-glow` | `--elev-1` / *(retired)* | `--elev-1: 0 8px 40px -12px rgba(0,0,0,0.6)` |
| *(none — palette inline)* | `--elev-2` | `0 30px 100px -20px rgba(0,0,0,0.8)` |
| *(none)* | `--dur-1/--dur-2/--dur-3` | `150ms/200ms/300ms` |
| *(none)* | `--dur-exit-1/--dur-exit-2/--dur-exit-3` | `100ms/130ms/200ms` |
| *(none)* | `--ease-enter` / `--ease-exit` | `cubic-bezier(0.22,1,0.36,1)` / `cubic-bezier(0.55,0,1,0.45)` |

Retired var names must not appear anywhere after Wave 2 (B greps for
`--brand-`, `--scan`, `--glass`, `--wall-` and fixes every hit in B-owned files;
A does the same in A-owned files).

### 1b. Type-size fixes (12px floor — every current violation)

| Location | Now | Becomes |
|---|---|---|
| `.wall-label` 0.72rem (11.52px) | violates | **0.75rem**, tracking 0.08em→0.06em |
| `.wall-mono` 0.7rem (11.2px) | violates | **0.75rem**, line-height 1.5 |
| `text-[11px]` sub-lines (StatBig, CenterStage, DataStreamFeed, FindingsTrend) | violates | `.wall-sub` = 13px (0.8125rem) |
| `text-[10px]` (RecentScans badge, FindingsTrend "N scans", EngineTelemetry labels, Heatmap axis) | violates | **12px** (0.75rem) |
| RankedPanel rule-id column `text-[10px]` | violates | 12px mono |

### 1c. JS-side color single-sourcing

`web/components/wall/tokens.ts` becomes the one JS color map the globe and any
canvas need (CSS vars can't feed three.js). Keep `SEV_COLOR` (now mapping to
`var(--sev-*)` names) and add `SEV_HEX: { certain:"#FF3B5C", high:"#FF8A3D",
medium:"#FFC83D", clean:"#2DE08A" }`. GlobeCore imports these and **deletes its
local `SEV_HEX`/`C` hexes** (decorative land/city/atmosphere colors stay local and
gain a comment "decorative brand backdrop — not data"). `lib/severity.ts` (SEVERITY
map, icons) remains the canonical severity icon/label source for both teams.

---

## 2. (a) Cockpit hierarchy — one dominant status statement

File: `web/app/dashboard/page.tsx` (+ `StatBig`, `FindingsSplit`, `RankedPanel`).

### 2a.1 Grid structure

Replace the 3-column flex children with **6 named grid sections** so mobile (§8)
can reorder without DOM surgery:

```
grid gap-3 px-3 py-2
  lg: grid-cols-[300px_minmax(0,1fr)_340px] grid-rows-[auto_auto_minmax(0,1fr)]
  lg: grid-template-areas:
      "hero center stream"
      "fix  center stream"
      "most center stream"
```

DOM order (also the mobile visual order): `hero` → `fix` → `center` → `stream`
(Data Stream + Recent Scans) → `most` (Most Flagged) → bottom strip (separate
grid below, unchanged position). Desktop column split: hero+fix+most = left rail
(300px), center = globe, stream = right rail (340px). Left rail keeps
`lg:border-r wall-divider lg:pr-3` hairline; right rail keeps the mirrored one.

### 2a.2 Hero — Quarantine Status (`hero` area)

One dominant statement answering "is my code clean". Replaces the three competing
heroes (Repos Scanned tile, Findings Today overlay, Findings Split tile lead).

- **Label:** `.wall-label` "Quarantine Status" + status icon 16px to its left:
  ShieldCheck `--sev-clean` (EVERY completed scan clean — branch on
  `cleanPasses === completed`, never the rounded rate: at ≥200 scans with one
  unclean scan, Math.round rounds the rate to 100 and would lie) · ShieldAlert
  `--sev-certain` (any completed scan not clean) · Shield `--text-muted` (no
  completed scans).
- **Figure:** the clean pass rate — `.wall-figure-hero`
  (clamp(3.25rem, 5.5vw, 4.75rem), weight 200, tabular), value = `data.cleanRate` +
  `%`. Color: `--sev-clean` when rate = 100, else plain `--text` (the percentage is
  a rate, not a finding — the severity chips carry the warm colors). No completed
  scans → figure renders "—" in `--text-muted`.
- **Statement line** (`.wall-sub`, 13px), exact copy rules:
  - completed = 0 → "No scans yet — run your first scan to see your quarantine status."
  - cleanRate = 100 → "All {completed} scans came back clean."
  - else → "{cleanPasses} of {completed} scans came back clean."
- **Inline severity chips** (`.wall-chip`, wrap allowed, gap 8px, each a button →
  `/analyses`): `[ShieldAlert] {blockEligible} block-eligible` (sev-certain) ·
  `[AlertTriangle] {highTotal} high` (sev-high) · `[Info] {mediumTotal} medium`
  (sev-medium). Icon + text + color, always. Chips render only when their count > 0.
- **Context line** (`.wall-sub`, `--text-muted`): "{completed} scans completed ·
  {scannedRecent} in last 10 min". If `data.incompleteCoverage > 0`, append
  " · [Info icon] {incompleteCoverage} with incomplete coverage" (13px,
  `--sev-medium`, honest caveat — never render a pass rate without it).
- **Whole tile** is a button → `/analyses` (`.wall-click .wall-focus`, min 44px).

Data: hero needs three NEW derive fields (§3.2). `cleanRate`/`cleanPasses`/
`completed`/`blockEligible` exist.

### 2a.3 Demotions

- **Most Flagged** (`most` area): moves below FixFirst in the left rail. Changes:
  top 5 rows (was 9); **full check names — remove `truncate`, allow wrap to 2
  lines** (no ellipsis on names; the rule-id column stays mono 12px); each row
  gains a severity icon (14px, from `lib/severity.ts` map, colored by the check's
  `sev`) left of the name; footer link "All checks →" → `/checks` (13px cyan,
  44px hit) so the rail fits. Identicon (22px), rank number, count stay. Empty
  state §7.
- **"Repos Scanned" StatBig is retired from the rail.** The scanned count lives on
  as the hero context line; the Analyses entry point is the hero tile itself and
  the dock tab. Do not add a fourth number tile.
- **CenterStage "Findings Today" overlay is retired** (§6.3) — total findings live
  in the bottom strip's "Findings Caught" tile (§5).

---

## 3. (b) FixFirst tile (NEW)

File: NEW `web/components/wall/FixFirst.tsx` (A), data from `useWallData.derive()`.

### 3.1 Visual spec (`fix` area, left rail, directly under hero)

- Header row: `.wall-label` "Fix First"; right side `.wall-sub` 13px
  "by block-eligible findings".
- Rows (max **5**), each a full-width `<button>` → `/analyses/{scanId}`:
  min-height 44px, radius `md`, padding 8px 8px, gap 10px, hover
  `background: rgba(255,255,255,0.04)`, focus `.wall-focus`.
- Row anatomy, left→right:
  1. **Rank** — `.wall-num` 12px, `--text-faint`, width 16px, right-aligned.
  2. **Severity badge** — `.wall-chip-sm` (icon + text + color, never color-only):
     lucide icon 14px + tier word "Certain"/"High"/"Medium" 12px, `--chip-color`
     set to the row's `--sev-*` (icons from `lib/severity.ts`:
     ShieldAlert/AlertTriangle/Info).
  3. **Middle (flex-1, min-w-0):**
     - Line 1 — check names from `topChecks`: "{name} ×{count}" joined by " · "
       (14px, `--text`, wrap to max 2 lines then `line-clamp: 2`). If
       `topChecks` is empty (pre-analytics row): "Rule breakdown unavailable for
       this scan" (13px, `--text-muted`, italic-free).
     - Line 2 — `.wall-mono` 12px: `{shortRef(ref)}` in `--text-muted` + " · " +
       `{formatRelativeTime(at)}` in `--text-faint`. Full `ref` in `title` and
       `aria-label` (refs may be long; single-line ellipsis is allowed here — the
       full text is the accessible name).
  4. **Right (shrink-0, text-right):** `blockEligible` as `.wall-num` 20px,
     `--sev-certain`; caption 12px `--text-muted` "block-eligible". Below it, only
     when `advisories > 0`: "· {advisories} advisory" 12px `--text-faint`.
- Entrance: rows stagger 40ms (§Motion), transform/opacity only.

### 3.2 Data contract — implement exactly in `useWallData.derive()`

Extend `WallData` (file `web/lib/useWallData.ts`, A-owned) and `web/lib/types.ts` (extend-only):

```ts
export interface FixFirstRow {
  scanId: number
  ref: string
  blockEligible: number      // analytics.block_eligible
  advisories: number         // max(0, analytics.total_findings - analytics.block_eligible)
  topChecks: { id: string; name: string; count: number }[] // ≤2, from by_rule, count desc
  sev: Sev                   // worst confidence tier present (existing worstSev())
  at: number                 // created_at epoch ms (recency tiebreak)
}
```

`WallData` gains: `fixFirst: FixFirstRow[]`, `highTotal: number`,
`mediumTotal: number`, `incompleteCoverage: number`, and `latestCompletedId:
number | null` (needed for the beam-sweep trigger, §10.4). `RecentTarget` gains
`filesScanned: number` (globe ring thickness, §6). `EMPTY` gains the zero values
(`[]`, `0`, `null`).

`fixFirst` derivation (ranks **recent scans by block-eligible count** — no per-scan
findings fetches; `listScans` caps at 50 rows, accepted in the plan):

```
scans.filter(s => s.status === "completed" && s.analytics != null
              && (s.analytics.block_eligible ?? 0) > 0 && s.created_at != null)
  .sort: block_eligible DESC, then created_at DESC (newer first), then id DESC
  .slice(0, 5)
  .map(s => ({
    scanId: s.id,
    ref: s.ref,
    blockEligible: s.analytics.block_eligible,
    advisories: Math.max(0, s.analytics.total_findings - s.analytics.block_eligible),
    topChecks: Object.entries(s.analytics.by_rule ?? {}).filter(([, n]) => n > 0)
      .sort((a, b) => b[1] - a[1]).slice(0, 2)
      .map(([id, count]) => ({ id, name: CHECKS[id]?.name ?? id, count })),
    sev: worstSev(s.analytics),
    at: new Date(s.created_at).getTime(),
  }))
```

`highTotal`/`mediumTotal` = sums of `analytics.by_confidence.HIGH` / `.MEDIUM` over
completed scans (mirror the existing `certainTotal` loop). `incompleteCoverage` =
count of completed scans where `analytics != null && analytics.fully_covered === false`.
`latestCompletedId` = max `id` among completed scans, else `null`.

**QA fixture contract (write first, watched red → green per the plan):** scans
A(block=3, created T-2h) · B(block=3, created T-1h) · C(block=1, created T-30m) ·
D(completed, block=0) · E(running) → `fixFirst` order is `[B, A, C]`; B.topChecks
length ≤ 2 sorted desc; E and D absent.

### 3.3 FixFirst empty states

- No completed scans at all → `.wall-empty`: ShieldCheck icon, title "Nothing to
  fix yet", body "Run your first scan — Fix First ranks scans by the findings
  that would block a merge.", CTA link "Open Scan" → `/scan`.
- Completed scans exist, all block-eligible = 0 → `.wall-empty`: ShieldCheck icon
  `--sev-clean`, title "All clear", body "No block-eligible findings in the last
  {completed} scans. Advisory findings still appear under Most Flagged." No CTA.

---

## 4. (c) Data Stream — filters + 12px floor

File: `web/components/wall/DataStreamFeed.tsx` (A).

- **Filter chips** (`.wall-filter`, row of 3, directly under the header):
  "All" · "Failed" · "Block-eligible". Selected chip: text `--text`, bg
  `rgba(255,255,255,0.06)`, border `--line-strong`; unselected: `--text-muted`.
  `aria-pressed` on each. Filter semantics — **all real fields**:
  - All → every audit entry.
  - Failed → `action === "scan.failed"`.
  - Block-eligible → `action === "scan.completed" && Number(details.block_eligible ?? 0) > 0`
    (the audit payload for `scan.completed` carries `block_eligible` — verified in
    `api/app/store.py complete_scan()`; no fabrication).
  - A count line renders after the chips: ".wall-sub {n} events" (filtered count).
- **Readable event names** — replace the stylistic tokens with plain names, one
  real action each (extend the TOKEN map, do not invent entries; unknown actions
  render the raw action string in `--text-muted`):

  | action | label | color |
  |---|---|---|
  | `scan.created` | "scan created" | `--act-queued` |
  | `scan.running` | "scan running" | `--act-running` |
  | `scan.completed` | "scan completed" | `--act-completed` |
  | `scan.failed` | "scan failed" | `--act-failed` |
  | `scan.shadow_block` | "shadow block" | `--sev-certain` |
  | `settings.updated` | "settings updated" | `--accent-violet` |

  (`scan.shadow_block` currently falls through to a raw uppercase fallback — give
  it the proper token. Its meta line shows "would block {n} · shadow only".)
- **Row anatomy** (12px mono floor): line 1 = 6px status dot (action color, with
  shape redundancy: failed rows prefix "!" before the dot is not needed — the
  label text itself carries meaning, so dot + readable name satisfies
  not-color-only) + event name in `--text` + "→" + target in `--text-muted`;
  line 2 = full ISO timestamp, mono 12px, `--text-faint` (retained — real and
  unambiguous); line 3 = meta (`findings — n`, reason, retain days) in
  `--text-faint`. Rows keep `#{id}`.
- Header: `.wall-label` "Data Stream" + Terminal icon; "Real-Time" sub-line
  becomes `.wall-sub` 13px; the header timestamp stays mono 12px.
- MAX_ROWS stays 30; mask fade stays; empty state §7.

---

## 5. (d) Bottom strip — honest relabels

Files: `FindingsSplit`, `ContribHeatmap`, `FindingsTrend`, `EngineTelemetry`
(`panels/BottomStats.tsx`), all in `page.tsx`'s bottom grid (4 tiles, unchanged
structure: findings split / trend / heatmap / engine).

- **Tile 1 — relabel.** `.wall-label` becomes **"Findings Caught"** (plain, single
  color — the mixed-color "Findings Cleared/Caught" label dies). Content stays:
  `.wall-figure-tile` total findings (`.wall-grad-cool` is retired from this
  figure — a findings count takes **no brand gradient**; render in plain `--text`
  so the severity chips below carry all color). Inline stats stay: block-eligible
  (sev-certain), advisory (muted), clean passes (sev-clean) — each count is a
  button → `/analyses`, whole tile keeps its click.
- **Tile 3 — Heatmap honesty.** Replace the fake "1 2 3 4 5" axis ticks with 3
  real date labels derived from the cell data: first cell's month/day, middle
  cell's, last cell's (format "Aug 18", 12px, `--text-faint`, `.wall-num`). Add a
  permanent caption under the axis: `.wall-sub` "**{scans.length} scans so far**"
  (real total — the 11-scan reality reads as "small but alive", not broken).
  Empty state (all cells 0): overlay copy "No scans in the last 13 weeks yet" +
  the caption. Keep the 4-bucket green ramp and Less→More legend; add a
  visually-hidden summary: "{n} scans across the last 13 weeks; busiest day
  {day} with {count}." (`scans.length` requires passing `data.scanned` into the
  component — extend its props).
- **Tile 2 — FindingsTrend:** keep (honest); 10px labels → 12px; add the same
  visually-hidden summary pattern ("latest {n}, peak {p} findings over {k}
  completed scans").
- **Tile 4 — EngineTelemetry: keep as-is** (it is the honest panel; no new
  readings). Only apply the 12px floor to its `Reading` labels (currently 11px)
  and the 10px Online/Offline pill → 12px.

---

## 6. (e) Honest globe overlays

Files: `CenterStage.tsx`, `GlobeCore.tsx` (A). Principle: **earth = decorative
brand backdrop (aria-hidden); every data layer on top is real.**

### 6.1 Data orbit rings (per recent scan)

- Source: `data.recentTargets` (≤8) now carrying `filesScanned` (§3.2).
- One tube ring per target, replacing the ambient *data-implying* arcs between
  points (the point-to-point arcs imply origin→destination geography scans don't
  have — **retire the arcs and their traveling dots**). Keep the three ambient
  decorative rings (opacity ≤ 0.16, explicitly decorative).
- Geometry: ring *i* (0 = newest) is a `TubeGeometry` circle, radius
  `1.06 + i * 0.02` (newest innermost), tilt: deterministic per index
  `Euler(0.35 + i*0.09, i*0.45, 0.12*i - 0.3)` — stable across polls so rings
  don't jump when the list shifts.
- **Thickness ∝ files_scanned:** tube radius = `0.004 + 0.008 * min(1, filesScanned / 5000)`.
- **Color = real status:** completed+clean → `--sev-clean` hex; completed with
  findings → `SEV_HEX[sev]`; failed → `#FF3B5C`; queued/running → `#16E0E0`
  (pulsing opacity 0.35+0.25·sin(t)). Opacity 0.45 for finished scans.
- **Labels + click:** each ring gets an invisible raycast proxy tube
  (radius ×3, opacity 0). Hover: ring material opacity → 0.9 + `.wall-tooltip`
  (HTML, follows pointer): "scan/{id} · {shortRef(ref)} · {status} · {filesScanned}
  files · {findings} findings". Click → `/analyses/{id}`. Cursor: pointer.
  The HTML twin for keyboard/screen readers is Recent Scans (§6.4) — the canvas
  itself is `aria-hidden="true"` with a visually-hidden paragraph above it
  naming the interactive twin.
- **Finding bursts:** keep the radial beams, honestly sized: length =
  `0.06 + min(0.22, sqrt(weight) * 0.035)` where weight = real findings count;
  color = `SEV_HEX[sev]`; clean scans keep the 0.06 nub in cyan-green.
  Marker sphere radius: `0.014 + min(0.03, sqrt(weight) * 0.004)`.
- **Finding bursts** render only for completed scans (no invented mid-scan counts).

### 6.2 Static frame fallback (reduced motion / no WebGL)

New sibling `GlobeStatic.tsx` (A) used when `useReducedMotion()` is true OR WebGL
is unavailable (wrap the `Canvas` mount in a try/catch capability check — if
`WebGLRenderingContext` is missing or context creation throws, render static).

- Inline SVG, viewBox 0 0 400 400, centered decorative earth disc
  (radial-gradient fill `#0A1126`, no land dots needed).
- One `<ellipse>` per recent scan (same radii/colors/thickness mapping scaled
  ×140, rotated to match the 3D tilts), `fill="none"`, `stroke-width` = mapped
  thickness × 40 (2–5px).
- Each ellipse wrapped in `<a href="/analyses/{id}" aria-label="Scan {shortRef(ref)}
  — {status}, {filesScanned} files, {findings} findings">` — keyboard operable
  without JS handlers.
- Caption line below: `.wall-ring-legend` (13px, `--text-muted`): "Orbits = last
  {n} scans · thickness = files scanned · colour = status".
- The static frame honors the same color/thickness/label contract — it is a
  fallback, not a dumbed-down cousin.

### 6.3 CenterStage overlay changes

- **Retire the "Findings Today" hero block** (top-left) — the cockpit hero (§2a.2)
  owns the status statement. Top-left instead gets the **orbit legend caption**:
  `.wall-ring-legend` "Orbits = last {n} scans · click a ring to open it".
- Keep: brand button top-right (aria-label "Home"), Settings gear bottom-left,
  interval + pause bottom-right. All icon buttons get 44px hit areas (currently
  24–28px — add padding, keep 16–24px icon visual).
- Caption/sub-lines: `.wall-sub` 13px (no 11px text anywhere).

### 6.4 Recent Scans (globe's HTML twin)

Rows become ≥44px (padding bump), badge text 12px, full `shortRef` shown (title +
aria-label carry the full ref). Otherwise unchanged — it is already honest.

---

## 7. (f) Empty / low-data states (11-scan reality)

Global rules:

- **First-scan storytelling:** when `scans.length === 0`, panels tell the user
  what will appear here and why it matters — never "No data" dead-ends.
- **"So far" framing:** counts always read as cumulative-and-growing ("N scans so
  far", "appear once issues are detected") — small numbers read alive, not broken.
- **Skeletons only > 300ms:** while `useWallData().loading` is true, panels render
  `.wall-skeleton` blocks **only after a 300ms timer** (mount a `useDelayedFlag(300)`
  hook; if data arrives first, no skeleton ever renders). Skeleton = 3 stacked
  blocks (h-3/h-3/h-8, radius `md`, opacity shimmer 1.2s). Under reduced motion
  the shimmer is static (kill switch) — acceptable.

Per panel:

| Panel | Zero-data copy (exact) | CTA |
|---|---|---|
| Hero | figure "—", statement "No scans yet — run your first scan to see your quarantine status." | tile click → /analyses |
| FixFirst | §3.3 (two variants) | "Open Scan" → /scan (first variant only) |
| Most Flagged | "No findings yet — ranked checks appear once issues are detected." | — |
| Data Stream | "Awaiting events — run a scan to populate the stream." | — |
| Recent Scans | "No scans yet — start one from the Scan tab." | — |
| FindingsTrend | "Trend appears after 2+ completed scans." | — |
| Heatmap | "No scans in the last 13 weeks yet" + "{0} scans so far" caption | — |
| Globe | earth + legend caption "Orbits appear after your first scan." | — |
| Engine | renders real zeros (Queue 0, Last 10 min 0, Avg —, Completed 0) — honest, no empty state | — |

Low-data (1–2 completed scans): FixFirst with 1 row is fine (do not pad); Trend
shows its 2+ message; Heatmap shows 1–2 lit cells — all honest, no artificial
fill.

---

## 8. (g) Mobile 390px spec

- **Stack order = DOM order** (§2a.1): Hero → FixFirst → globe banner → Data
  Stream → Recent Scans → Most Flagged → bottom strip. No `order` tricks needed.
- **Globe becomes a banner:** `center` section height `40vh` (min 320px) on
  <1024px; the 3D canvas, raycast hits, and overlays all work at banner size;
  overlays keep their corners. `lg:` returns to full-height center column.
- **Bottom strip:** `grid-cols-1` < 768px → `grid-cols-2` at 768 → `grid-cols-4`
  at lg. Borders: only horizontal dividers between stacked tiles (no stray
  `border-r` — audit the current `max-lg:border-r-0` patch and replace with
  border utilities per breakpoint).
- **Touch targets ≥44px everywhere** — rail rows (FixFirst, Recent, Most Flagged),
  filter chips (visual 32px + pseudo-element hit extension to 44px on
  `pointer: coarse`), dock tabs, palette rows, icon buttons. 8px minimum gap
  between adjacent targets.
- **No horizontal scroll:** hero figure clamp min 3.25rem fits 358px content
  width; chips wrap; FixFirst rows wrap (name clamp 2 lines); mono ISO timestamp
  (~24ch ≈ 173px) fits; `.wall-figure-hero` gets `overflow-wrap: normal` and the
  tile `min-width: 0` everywhere. Verify at 390 AND 320.
- **Inputs ≥16px font** (`.wall-input`, palette input) — prevents iOS focus zoom.
- **Type floor holds on mobile** — 12px floor is breakpoint-independent.
- Viewport: keep `width=device-width, initial-scale=1` (never disable zoom);
  `min-h-dvh` on the shell (already present).

---

## 9. (h) Chrome — one system across dock, palette, boot, login

### 9.1 CommandDock (B)

- Tab links: min-height **44px**, padding 0 12px, radius `md`, 13px text, sentence
  case (no caps). Active: text `--text`, bg `rgba(255,255,255,0.06)`, 1px
  `--line-strong` border, `aria-current="page"` (kept). Hover: text `--text`.
- Brand mark: keep 28px gradient tile + ShieldCheck (`--on-accent` icon);
  wordmark keeps tracked-caps (brand exception). Gradient = merged
  `--brand-gradient`.
- ⌘K pill: visual 28px, hit 44px (pseudo-element), border `--line`, mono 12px.
- Live pill: dot + "Live"/"Offline" 12px (was 11px). Dot `--accent-green` pulsing
  (pulse is an ambient state signal — allowed; static under reduced motion).
- Hairline bar stays (brand moment, dock only). Header total height ≈ 48px+2px.

### 9.2 CommandPalette (B)

- Panel: `.wall-card` at radius `xl` + `--elev-2`, over scrim `rgba(2,4,10,0.6)`
  + blur 6px (kept). Width min(560px, 92vw) kept.
- Input: 16px text, 48px row height, `--text`, placeholder `--text-faint`.
- Rows: min-height **44px**, radius `md`, hover `rgba(255,255,255,0.05)`, 14px
  text, icons 16px (`--accent-cyan` for the scan-URL row, `--text-muted` for jumps).
- Keyboard (keep Tab trap + Esc): add `role="listbox"` on the list,
  `role="option"` + `aria-selected` per row, **ArrowUp/ArrowDown** moving
  `aria-activedescendant`, Enter activates the highlighted row (currently
  Enter only submits a URL — generalize).

### 9.3 BootScreen (B)

- Replace the hardcoded radial (`#05070f/#02030a/#000000`) with tokens:
  `radial-gradient(125% 95% at 50% 30%, var(--bg-glow) 0%, var(--bg-deep) 55%, #000000 100%)`.
- Swap the text glyphs ✓ / ▸ for lucide `Check` (14px, `--accent-green`) /
  `ChevronRight` (14px, `--text-faint`) — no unicode-icon look.
- Boot lines: 12px mono floor (currently 11px). Progress bar violet→cyan gradient
  kept (brand moment). Wordmark keeps `.wall-grad-cool` + tracked-caps (brand
  exception). Timings kept (2.2s / 0.4s reduced).

### 9.4 Login (B) — drop the leftover Aurora skin

- `app/login/page.tsx`: wrapper becomes `.wall-root` (gains the starfield + token
  backdrop; replaces `bg-bg` which carries the retired #06080A). MatrixRain stays
  (B-owned effect, decorative, `aria-hidden`); center scrim stays.
- `SignInFlow.tsx` class migration (exact):
  - `text-text` → inline `color: var(--text)` or new tailwind names (§11);
    `text-text-muted` → `--text-muted`; `text-text-faint` → `--text-faint`.
  - `bg-surface/60` + `backdrop-blur` pills → solid `--surface` + 1px
    `--line-strong` (the blur-as-decoration rule).
  - `rounded-full` on Google button / input / divider container → radius `md`
    (8px). Inputs min-height 44px, 16px text.
  - `focus:ring-brand-indigo/40` → `.wall-focus` (2px solid cyan).
  - `bg-brand-gradient` on the submit circle and success check → merged
    `--brand-gradient`, icon/text `--on-accent`.
  - `text-sev-certain` error → unchanged token name after map (`--sev-certain`).
  - Primary "Continue" button (shadcn) → `.wall-cta` styling; "Back" →
    `.wall-cta-secondary`.
  - Code inputs: 6 cells, each ≥44×44px hit, 20px mono text, radius `md`, 1px
    `--line-strong` borders on the group container.
  - Framer transitions: 0.35s → `--dur-3` (300ms) enter / `--dur-exit-3` (200ms)
    exit, `--ease-enter`/`--ease-exit`.
- Google "G" glyph: replace the letter with the official four-color G SVG (brand
  asset rule) at 18px, or a lucide `Chrome` icon at 18px if the SVG is not
  available — never a styled letter.

### 9.5 Cross-cutting chrome rules (B applies to all B-owned surfaces)

- Token rename map (§1a) applied to every B-owned file; zero hits remain for
  `--brand-`, `--scan`, `--glass`, `--wall-`, `bg-bg` value drift.
- 12px type floor (§1b) and 44px targets everywhere, including WallPage,
  ScanConsole, ScanResults, AnalysesExplorer, ChecksCatalog, SettingsPanel,
  ActivitySpectrum, AnimatedScan, WallOverlay, findings components.
- Severity badges in findings/detail components use `.wall-chip` (icon+text+color)
  with colors from `lib/severity.ts`.
- Toasts: 13px text, sentence case (no caps), `--surface` + `--elev-1`, 4s
  auto-dismiss, `aria-live="polite"`.
- Error/reconnect banners on the cockpit: tokenized (error banner: bg
  `rgba(255,59,92,0.07)`, border `rgba(255,59,92,0.22)`, text `--sev-certain`,
  12px, add `role="alert"`; reconnect toast keeps `role="status"` +
  `aria-live="polite"`, cyan tokens, auto-dismiss 3s kept).

---

## 10. (i) wall.css contract — everything frontend-A lands in one pass

### 10.1 `:root` token block (NEW in wall.css — becomes the global source)

Wall.css is imported globally (`AppShell`), so this `:root` block is the single
home of every token in §DESIGN.md:

```css
:root {
  --bg: #04060c;
  --bg-deep: #02030a;
  --bg-glow: #0a1024;
  --surface: #0a0e18;
  --surface-translucent: rgba(12, 17, 28, 0.55);
  --line: rgba(120, 160, 255, 0.1);
  --line-strong: rgba(120, 160, 255, 0.2);
  --accent-cyan: #16e0e0;
  --accent-magenta: #ff3d8b;
  --accent-violet: #8b5cf6;
  --accent-green: #2de08a;
  --brand-gradient: linear-gradient(110deg, #ff3d8b 0%, #8b5cf6 50%, #16e0e0 100%);
  --act-queued: #ff3d8b;
  --act-running: #16e0e0;
  --act-completed: #2de08a;
  --act-failed: #ff3b5c;
  --sev-certain: #ff3b5c;
  --sev-high: #ff8a3d;
  --sev-medium: #ffc83d;
  --sev-clean: #2de08a;
  --text: #eaf0ff;
  --text-muted: #8a95ad;
  --text-faint: #6f7890;
  --on-accent: #04060c;
  --elev-1: 0 8px 40px -12px rgba(0, 0, 0, 0.6);
  --elev-2: 0 30px 100px -20px rgba(0, 0, 0, 0.8);
  --dur-1: 150ms; --dur-2: 200ms; --dur-3: 300ms;
  --dur-exit-1: 100ms; --dur-exit-2: 130ms; --dur-exit-3: 200ms;
  --ease-enter: cubic-bezier(0.22, 1, 0.36, 1);
  --ease-exit: cubic-bezier(0.55, 0, 1, 0.45);
}
```

The old `.wall-root, .wall-vars { … }` variable block is **deleted** (vars are
global now); `.wall-root` keeps only layout (backdrop, starfield, isolation).
`.wall-vars` is retired (portals inherit `:root`).

### 10.2 Changed utilities (edits to existing)

| Utility | Change |
|---|---|
| `.wall-label` | font-size 0.72rem → **0.75rem**; letter-spacing 0.08em → **0.06em** |
| `.wall-mono` | 0.7rem → **0.75rem**; line-height 1.45 → **1.5** |
| `.wall-tab` | min-height 40px → **44px**; radius 10px → **8px** |
| `.wall-cta` | radius 12px → **8px**; add `color: var(--on-accent)` (replaces literal #04060c) |
| `.wall-cta-secondary` | radius 12px → **8px**; min-height 44px kept |
| `.wall-input` | radius 10px → **8px**; add `min-height: 44px`; font-size → **16px**; focus: `box-shadow: 0 0 0 2px var(--accent-cyan)` (2px, was 1px) |
| `.wall-card` | bg → `var(--surface)`; border-color → `var(--line-strong)`; radius 14px → **12px**; add `box-shadow: var(--elev-1)` |
| `.wall-click` | transitions use `var(--dur-1) var(--ease-enter)` |
| `.wall-focus` | keep 2px cyan; radius 8px kept |
| `.wall-grad-pink` | **delete** (brand-flavored gradient on findings figures — retired, no replacement) |
| `.wall-grad-cool` | keep (brand moments only: wordmark, decorative figures) — never on findings/severity numbers |
| `.wall-grad-warm` | redefine: `linear-gradient(110deg, var(--sev-high) 0%, var(--sev-certain) 100%)` — findings figures only |
| `.wall-hairline` | keep, dock only |
| `.wall-glow-cyan/-magenta` | keep; hero figure + wordmark only |

### 10.3 NEW utilities

```css
/* Secondary line — replaces every text-[11px]/text-[10px] sub-line. */
.wall-sub { font-size: 0.8125rem; line-height: 1.5; color: var(--text-muted); }

/* Cockpit hero figure. */
.wall-figure-hero {
  font-family: var(--font-sans), sans-serif;
  font-variant-numeric: tabular-nums; font-weight: 200;
  letter-spacing: -0.02em; line-height: 0.92; color: var(--text);
  font-size: clamp(3.25rem, 5.5vw, 4.75rem);
}
/* Tile lead figure (Findings Caught). */
.wall-figure-tile {
  font-family: var(--font-sans), sans-serif;
  font-variant-numeric: tabular-nums; font-weight: 200;
  letter-spacing: -0.02em; line-height: 0.92; color: var(--text);
  font-size: clamp(2rem, 3.5vw, 3rem);
}

/* Severity/summary chip: icon + text + color (never color-only).
   Set --chip-color per instance; icon inherits it. */
.wall-chip {
  display: inline-flex; align-items: center; gap: 6px;
  height: 28px; padding: 0 10px; border-radius: 6px;
  font-size: 0.75rem; font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--chip-color, var(--text));
  background: color-mix(in srgb, var(--chip-color, var(--text)) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--chip-color, var(--text)) 24%, transparent);
}
.wall-chip-sm { height: 24px; padding: 0 8px; }

/* Stream filter chip — 32px visual, 44px hit on coarse pointers. */
.wall-filter {
  display: inline-flex; align-items: center; gap: 6px;
  min-height: 32px; padding: 0 12px; border-radius: 6px;
  font-size: 0.75rem; color: var(--text-muted);
  border: 1px solid var(--line); background: transparent;
  position: relative; transition: color var(--dur-1) var(--ease-enter),
    border-color var(--dur-1) var(--ease-enter), background var(--dur-1) var(--ease-enter);
}
.wall-filter::after { content: ""; position: absolute; inset: -6px; }
@media (pointer: coarse) { .wall-filter { min-height: 44px; } }
.wall-filter-on { color: var(--text); background: rgba(255, 255, 255, 0.06); border-color: var(--line-strong); }

/* Empty state. */
.wall-empty { display: flex; flex-direction: column; gap: 8px; padding: 16px; }
.wall-empty-icon { color: var(--text-muted); margin-bottom: 4px; } /* lucide 20px */
.wall-empty-title { font-size: 0.875rem; font-weight: 600; color: var(--text); }
.wall-empty-body { font-size: 0.8125rem; line-height: 1.5; color: var(--text-muted); }
.wall-empty-cta { font-size: 0.8125rem; color: var(--accent-cyan); text-decoration: underline;
  text-underline-offset: 4px; min-height: 44px; display: inline-flex; align-items: center; }

/* Skeleton — mounted only after a 300ms load delay (JS gate). */
.wall-skeleton { border-radius: 8px; background: rgba(255, 255, 255, 0.05);
  animation: wall-shimmer 1.2s ease-in-out infinite; }
@keyframes wall-shimmer { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.8; } }

/* Globe hover tooltip. */
.wall-tooltip { position: fixed; z-index: 50; pointer-events: none;
  background: var(--surface); border: 1px solid var(--line-strong);
  border-radius: 6px; padding: 6px 10px; box-shadow: var(--elev-1);
  font-size: 0.75rem; font-variant-numeric: tabular-nums; color: var(--text); }

/* Orbit legend caption. */
.wall-ring-legend { font-size: 0.8125rem; line-height: 1.5; color: var(--text-muted);
  font-variant-numeric: tabular-nums; }
```

### 10.4 The signature beam sweep (NEW)

```css
.wall-sweep { position: absolute; inset: 0; z-index: 30; pointer-events: none;
  animation: wall-sweep 700ms ease-in-out 1 both; }
.wall-sweep::before { content: ""; position: absolute; left: 0; right: 0; top: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent 0%, var(--accent-cyan) 50%, transparent 100%);
  box-shadow: 0 0 24px rgba(22, 224, 224, 0.6); }
@keyframes wall-sweep { from { transform: translateY(-100%); } to { transform: translateY(100%); } }
```

Trigger (A, in `page.tsx`): track `data.latestCompletedId`; when it changes from
a non-null value to a new value, mount `<div className="wall-sweep" />` inside the
`.wall-root` scope (AppShell passes children within it; the sweep element may
live in the page's fragment — `.wall-root` is `relative`), unmount after 750ms.
Skip entirely when `useReducedMotion()` is true or `document.hidden`. Multiple
completions while hidden coalesce to one sweep on return.

### 10.5 Count-up (A, hero + tile figures)

Hook `useCountUp(value: number, { duration = 600, disabled })` — RAF-based,
ease-out, renders the raw value instantly when `useReducedMotion()` is true.
Applies to the hero percentage and the Findings Caught figure (mount + every
change). Tabular figures keep width stable.

### 10.6 Skeleton delay hook (A)

`useDelayedFlag(active: boolean, ms = 300): boolean` — returns true only when
`active` has held for `ms`. Gates every skeleton render (§7).

---

## 11. globals.css + tailwind contract — everything frontend-B lands

- **globals.css keeps:** `@tailwind` directives, `@layer base` (body font/color
  via `--text`, `h1–h3` display font, `.tnum`), the global reduced-motion kill
  switch. **Deletes:** the entire Aurora `:root` token block, `.glass`,
  `.text-gradient` (retired — no replacement needed).
- **tailwind.config.ts:** color names re-pointed to the merged vars —
  `bg: rgb-triple var(--bg)` needs RGB triples; keep the existing `-rgb` triple
  pattern and define triples for the new tokens (bg `4 6 12`, surface `10 14 24`,
  text `234 240 255`, text-muted `138 149 173`, text-faint `111 120 144`,
  accent-cyan `22 224 224`, accent-magenta `255 61 139`, accent-violet `139 92 246`,
  accent-green `45 224 138`, sev-* as existing). Names: `bg`, `surface`,
  `surface-elevated` (alias of `--surface`), `line`, `line-strong`,
  `accent-cyan/-magenta/-violet/-green`, `sev-certain/-high/-medium/-clean`,
  `text`, `text-muted`, `text-faint`. **Delete:** `brand-indigo`, `brand-teal`,
  `scan`, `border`, `border-strong`, `bgImage brand-gradient` → re-point
  `brand-gradient` to the merged var. Radius: `xs 4 / sm 6 / md 8 / lg 12 /
  xl 16 / full` (shadcn components using `rounded-md/lg` pick up the new scale
  automatically). Font sizes: floor-safe scale `xs 12 / sm 13 / base 14 / md 16 /
  lg 18 / xl 20 / 2xl 24 / 3xl 32`. Keyframes `aurora-drift` + `orbit-spin/pulse`
  retire with their effects; keep `scan-pulse` (live shimmer), `dot-reveal`,
  `lollipop-grow` if still referenced after B's grep.
- **AppShell:** no structural change (wall.css import + dock + palette stay).
  `/login` bypass stays, but login's own wrapper becomes `.wall-root` (§9.4).

---

## 12. QA checklist (verify in this order — priority ladder)

1. **Accessibility:** contrast — muted 6.7:1, faint 4.6:1, all sev colors ≥4.5:1
   as text on `--bg` (crimson 5.8, amber 8.6, gold 13.1, green 12.1, cyan 12.3,
   violet 4.8 — violet text only at ≥13px/500); severity icon+text+color on every
   chip/badge/dot; `.wall-focus` on every interactive element; keyboard: palette
   arrow-nav + Esc, ring interactions have the Recent Scans twin, tab order =
   visual order; `role="alert"` error banner; `aria-live` toasts; heatmap/sparkline
   sr-only summaries; no color-only state anywhere.
2. **Touch:** every interactive element ≥44px (chips via hit extension on coarse
   pointers); 8px gaps; inputs 44px + 16px font.
3. **Performance:** skeletons only >300ms; globe DPR capped [1,2], frameloop
   demand when paused/hidden; geometry disposal kept; no layout shift (tabular
   figures; heatmap/hero reserve space); transform/opacity-only animations.
4. **Style:** one token set (grep: zero `--brand-`, `--scan`, `--glass`,
   `--wall-` hits); no emoji icons; lucide-only, 14/16/20px; gradients only on
   CTA/wordmark/hairline/hero-brand moments.
5. **Layout:** 1440 grid areas match §2a.1; 390 order matches §8; no horizontal
   scroll at 390 and 320; bottom strip 1/2/4 columns.
6. **Type/color:** 12px floor (no 10px/11px/0.7rem/0.72rem anywhere); tracked-caps
   only on `.wall-label` + wordmark; tabular figures on every number.
7. **Animation:** 150/200/300 + 65% exits; 40ms stagger ≤8; count-up 600ms;
   beam sweep fires exactly once per new completion and never under reduced
   motion; global reduced-motion kill switch intact.
8. **Forms:** login inputs labeled, errors below field, focus moves to code cell
   on step change (kept), disabled states ≥0.5 opacity + `disabled` attribute.
9. **Nav:** dock active state via `aria-current`; palette deep-links (kept);
   back preserves panel state via `usePanel` (kept).
10. **Charts:** heatmap tooltips + sr summary; sparkline sr summary; globe static
    fallback = focusable SVG links with full aria-labels; data colors ≥3:1 (all
    pass, §1 of this checklist).
