# plan-dashboard-overhaul — Command Wall max overhaul (FEATURE MODE)

> build-head slice plan for `feat/dashboard-overhaul`. Approved by user 2026-11-12.
> Execution: implement team playbook (waves). Zero backend changes.

## Product framing

The Command Wall is the operator cockpit of AI Slop Quarantine Guard: it answers
three questions at a glance — **is my code clean?** (quarantine status), **what do
I fix first?** (prioritized queue), **is the engine healthy?** (honest telemetry).
Today it is a beautiful cockpit that answers none of those first. This overhaul
keeps the black-starfield neon identity and rebuilds the information layer so the
spectacle is made of *real data* — the project's "never lie about a fact" promise
applies to pixels as much as to findings.

## In / out of scope

**In:** one unified design system (Aurora + Wall merged); hero hierarchy (one
dominant status statement); honest globe (scans as labeled clickable orbit rings,
bursts sized by real counts, earth = decorative brand only); FixFirst queue;
Data Stream filters + 12px floor; honest relabels + designed empty states;
truncation fixes; mobile 390px first-class; legacy orphan cleanup + dep pruning;
vitest suite; never-lie security sweep.

**Out:** any `api/` change, auth enablement, merging open PRs #20–25, new
endpoints, brand rename.

## Architecture bets (with reversal costs)

1. **All operator intelligence stays client-side**, derived in `web/lib/useWallData.ts`
   `derive()` from existing `GET /api/scans` + `/api/audit`. Reversal: cheap (swap
   to server aggregation later). Risk: `listScans` caps at 50 rows — FixFirst v1
   ranks *recent scans by block-eligible count* (from `ScanSummary.analytics`), each
   linking to `/analyses/[id]`; it does NOT fetch per-scan findings. Accepted:
   v1 ships without extra requests.
2. **One token system, two ramps** (neon = brand/identity; warm = severity only).
   Severity never color-only. Reversal: trivial (CSS vars).
3. **Globe keeps three.js** but its data layers become honest; DPR capped, paused
   offscreen, static frame for reduced-motion/no-WebGL (patterns already exist in
   GlobeCore). Reversal: medium — if perf disappoints, globe degrades to CSS
   starfield and FixFirst takes center stage.

**Riskiest assumption:** the summary endpoint carries enough per-scan signal
(`analytics.by_rule`, `block_eligible`) for a useful FixFirst without detail fetches.
**First test:** QA writes the `derive()` test asserting FixFirst input ranking from
summary fixtures BEFORE the cockpit implementation lands (watched red → green).

## Sequencing

Wave 1 team-uxui (design system spec) → Wave 2a/2b team-frontend (parallel, disjoint
file ownership) → Wave 3 team-qa + team-security (parallel) → Wave 4 build-pr.

## File-ownership map (no overlap; wall.css protocol below)

**team-uxui (Wave 1):** `docs/design/dashboard-overhaul.md`, rewrite `web/DESIGN.md`.

**team-frontend A — cockpit:**
`web/app/dashboard/page.tsx`, `web/app/dashboard/wall.css`,
`web/components/wall/{CenterStage,GlobeCore,StatBig,RankedPanel,DataStreamFeed,RecentScans,Identicon,tokens.ts}`,
`web/components/wall/panels/BottomStats.tsx`, NEW `web/components/wall/FixFirst.tsx`,
`web/lib/{useWallData.ts,types.ts}` (extend only), `web/lib/checks.ts` (only if catalog display needs it).

**team-frontend B — system + cleanup:**
`web/app/globals.css`, `web/tailwind.config.ts`, `web/app/layout.tsx`,
`web/components/layout/{AppShell,BootScreen}.tsx`,
`web/components/wall/panels/{CommandDock,CommandPalette,WallPage,ScanConsole,ScanResults,AnalysesExplorer,ChecksCatalog,SettingsPanel,ActivitySpectrum,AnimatedScan,WallOverlay}.tsx`,
`web/components/findings/*`, `web/components/wall/charts/RadialCharts.tsx`,
`web/components/auth/*`, `web/components/effects/*`,
`web/app/{scan,analyses,analyses/[id],checks,settings,login}/page.tsx`,
`web/package.json` (prune unused deps + add vitest dev-deps + `test` script),
legacy orphan deletions (grep-verified zero importers first).

**wall.css protocol:** A owns wall.css. Wave 1 defines ALL tokens/utilities up
front; A lands them; B consumes only. If B needs a new utility, it reports the
need; orchestrator relays to A. B never edits wall.css.

**team-qa (Wave 3):** `web/vitest.config.ts`, `web/tests/**` (derive logic, checks
catalog integrity, component tests: empty states, severity-not-color-only, FixFirst
ordering, keyboard nav). Every new-behavior test recorded failing first.

**team-security (Wave 3):** read-only sweep + findings report
`production/reviews/overhaul-security-sweep.md`. Secret redaction in evidence,
no fabricated telemetry, honest error/reconnect states.

**build-pr (Wave 4):** verdict `production/reviews/overhaul-build-pr.md`.

## Quality floor

`npx tsc --noEmit` + `npm run build` + `npx vitest run` all green; app launched
and exercised (scan run from /scan, wall updates); visual check 1440/768/390;
no emoji icons; contrast ≥4.5:1 body / ≥3:1 large; touch targets ≥44px;
`prefers-reduced-motion` honored. Machine notes: npm installs stay inside `web/`;
default `python` is 3.9 (use `py -3.14` if ever needed); console is cp1252.
