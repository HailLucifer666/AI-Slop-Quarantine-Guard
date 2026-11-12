# Overhaul Build-PR — Wave 4 final review (feat/dashboard-overhaul)

Date: 2026-11-12 · Reviewer: build-pr (Wave 4) · Method: kee review discipline + scope gates
A/C/E · Diff: working tree vs HEAD (`fa2d878`, main tip). ~71 tracked files changed (28 staged
deletions, 43 modified), 15 untracked new files (FixFirst, GlobeStatic, hooks, vitest.config,
tests/). Gates re-run by me, directly: `npx tsc --noEmit` = 0 errors; `npx vitest run` = 60/60
across 9 files. `npm run build` NOT re-run (brief forbids builds) — accepted from the Wave-3
result (success, 10 routes).

VERDICT: PASS WITH NOTES

The overhaul implements the Wave-1 spec (docs/design/dashboard-overhaul.md §a–§i) faithfully:
one merged token system, honest cockpit hierarchy with a real FixFirst queue, honest globe
rings with a working static fallback, real-field Data Stream filters, the 12px type floor,
honest relabels and designed empty states, mobile-first stacking, and the login migration.
The P2 "clean overstatement" fix is verified correct at all three sites. No fabricated data
found on any realistic path. Two real defects worth fixing at commit time (hero rounding edge,
unreachable "Offline" pill), neither of which lies on a path reachable with the current data
reality. The P1 backend snippet leak (placeholders.py/sast.py) remains open and OUT of this
branch's scope per the plan — it must be fixed before ship, in a backend change.

## Findings

### [IMPORTANT] [CONFIRMED] Hero "All clean" branch keys off the ROUNDED rate — at ≥200 completed scans with exactly one unclean scan, the hero shows 100%, a green ShieldCheck, and the sentence "All N scans came back clean." — web/app/dashboard/page.tsx:56-58,68,75-76 and web/lib/useWallData.ts:296

Why it matters end to end: `derive()` computes `cleanRate = Math.round((cleanPasses / completed) * 100)`
(useWallData.ts:296). With 199/200 clean, that is `Math.round(99.5)` = 100 — verified by running
the arithmetic: `Math.round((199/200)*100)` → 100, `Math.round((198/200)*100)` → 99. Hero then
takes the `rate === 100` branch three times: icon → ShieldCheck/--sev-clean (page.tsx:56-58),
figure color → --sev-clean (page.tsx:68), statement → "All 200 scans came back clean."
(page.tsx:75-76). One scan that found something is reported as all-clean — the exact lie class
this overhaul exists to kill, and the spec's own branch condition (§2a.2: "cleanRate = 100 → All
{completed} scans came back clean") carries the bug into the build. Unreachable until ~200 scans
with a single-digit failure count (11-scan reality today), and self-correcting as failures
accumulate, so it does not block this branch — but it must not survive to a long-lived install.

Fix: branch on the raw counts, not the rounded rate. In `Hero`, replace every `rate === 100`
with a new prop `allClean: boolean` computed in page.tsx as `data.cleanPasses === data.completed
&& data.completed > 0` (or have derive() export it). Keep `rate` for the figure color only
(`rate === 100` on the rounded figure is fine as a color choice). Regression test to add:
render `Hero` with `completed=200, cleanPasses=199, rate=100` and assert the statement does NOT
contain "All 200 scans came back clean" and the icon is not ShieldCheck. Note in the design doc
that §2a.2's branch condition is defined on the raw counts.

### [ADVISORY] [CONFIRMED] CommandDock's Live/Offline pill can never read "Offline" — the rebuilt component takes `live = true` by default and AppShell never passes real reachability — web/components/wall/panels/CommandDock.tsx:18, AppShell.tsx:49

Why it matters: AppShell renders `<CommandDock onPalette={...} />` with no `live` prop, so the
default `live = true` wins forever. While the dashboard error banner honestly reports an outage
(page.tsx:206-214, role="alert"), the always-visible dock keeps showing a pulsing green dot
labelled "Live" — an outage reading as healthy from the chrome, the same "dead honesty" class
the security sweep flagged for trustStatus (useWallData.ts:93-94, still unrendered). The spec's
§9.1 Live/Offline pill implies both states are real; the Offline half is unreachable as wired.

Fix: either wire it — lift `online` out of the dashboard (small event/ctx from `useWallData`, or
AppShell polls `/api/scans` itself) and pass `live={online}` — or delete the Offline claim and
render the pill as a brand moment only. Both resolve it; pick one before commit.

### [ADVISORY] [CONFIRMED] Dead, wrong fixture constants exported from tests/fixtures.ts — tests/fixtures.ts:227-287

`EXPECTED_FIXFIRST` and `EXPECTED_TOTALS` are exported but consumed by no test (grep across
tests/ = definitions only). Worse, `EXPECTED_TOTALS` is stale: it says `certainTotal: 4`
("G:2 + A:2") and `highTotal: 4` ("A:1 + F:3"), but the live derive fixture includes B
(CERTAIN:1, HIGH:2) and the actual passing assertion is certainTotal 5, highTotal 6
(useWallData.derive.test.ts:76-79). A future test consuming these constants fails confusingly,
or worse, someone "fixes" the passing test to match the stale constant.

Fix: delete both constants, or correct them to the real values with a comment naming
useWallData.derive.test.ts as the authority.

### [ADVISORY] [CONFIRMED] Boot splash names a rule that does not exist: "loading analyzers · SQG001–009" — web/components/layout/BootScreen.tsx:13

The catalog test pins SQG008 as absent by design (tests/checks.catalog.test.ts:49-53) and the
client catalog runs SQG001–007 plus SQG009 (web/lib/checks.ts). The range "SQG001–009" implies
nine contiguous rules including SQG008. Small, decorative, but the project promise is that
pixels don't lie about facts either.

Fix: `“loading analyzers · SQG001–007 · SQG009”`, or drop the range for
"loading analyzers · 8 checks".

### [ADVISORY] [CONFIRMED] Sign-in code cells are 44px tall but 32px wide — web/components/auth/SignInFlow.tsx:211

Spec §9.4: "6 cells, each ≥44×44px hit". Implemented `h-[44px] w-8` (w-8 = 32px). Height is
compliant; width is below the 44px touch floor. Everything else in §9.4 is conformant (radius
md, 20px mono, wall-cta/wall-cta-secondary, Chrome icon, on-accent gradient).

Fix: `w-11` (44px), or keep the visual 32px and add a `::after` inset hit extension like
`.wall-filter` / the ⌘K pill do.

### [NIT] [CONFIRMED] FixFirst check-name line is 13px, spec §3.1 says 14px — web/components/wall/FixFirst.tsx:51,55

`text-sm` under the remapped scale = 0.8125rem = 13px; §3.1 line 1 specifies 14px (`text-base`
in the new scale). The 12px floor holds; this is a one-class deviation from the spec's exact
value. Fix: `text-base` on both spans, or amend §3.1 to 13px — either resolves it.

### [NIT] [CONFIRMED] Reconnect toast is 12px, §9.5 specifies 13px for toasts — web/app/dashboard/page.tsx:302

`text-xs` = 12px on the "Connection restored" toast; §9.5 says toasts are 13px. Fix:
`text-sm` (13px). Trivial.

### [NIT] [PLAUSIBLE] Spec-vs-implementation deviations that are acceptable as made — page.tsx:30-33, FindingsSplit.tsx:5-9

§2a.2 says hero severity chips are "each a button → /analyses" and §5 says each inline count is
a button; both are implemented as spans inside the tile's single button. The code documents why
(nested `<button>` is invalid HTML; every chip shares the tile's destination) and the click
behavior is identical. Accepted — record it as a conscious spec amendment, not drift. Same for
FixFirst's line-1 font (above) if you choose to amend the spec.

### [NOTE] Open security-sweep items carried forward (pre-existing, out of this branch's scope)

- **P1 backend snippet leak** (api/app/analyzers/placeholders.py:108, sast.py:187,222) — still
  open, backend-only, explicitly excluded by the plan. Must land before any ship that scans
  hostile repos; the LLM-forward path (FindingCard → /api/crew/explain) makes it the priority.
- Sweep P3s still open in this tree, unchanged from the sweep and acceptable as follow-ups:
  audit-feed failure still renders as an empty stream (useWallData.ts:330 `.catch(() => [])`);
  AnalysesExplorer poll failure still hides errors after first load (AnalysesExplorer.tsx:158);
  trustStatus/hasRecentFailure still computed but unrendered (useWallData.ts:93-94);
  `@types/three` still in `dependencies` (package.json:23 — types-only, ships nothing, move to
  devDependencies when the lock file is next touched).

## What held (checked and passing)

**Token seam (both directions, grep-verified).** Every `var(--x)` referenced in app/components/lib
resolves: the 36 tokens defined in wall.css `:root` (§10.1 verbatim), `--chip-color` set
per-instance with an `var(--text)` fallback, and `--font-sans/--font-display/--font-mono` supplied
by next/font on `<html>` (app/layout.tsx:7-9,18). The only other `:root` is globals.css's
`--*-rgb` channel triples — disjoint names, and I verified each triple matches its wall.css hex
(bg 4 6 12 = #04060c … text-faint 111 120 144 = #6f7890). No token is defined twice with
different values. Zero hits anywhere for retired names: `--brand-`, `--scan`, `--glass`,
`--wall-*` (all variants), `--shadow-glass/glow`, `.glass`, `.text-gradient`, `.wall-vars`,
`.wall-grad-pink`. Tailwind names re-pointed correctly (colors → rgb triples, line/line-strong →
vars, brand-gradient → merged var, radius xs4/sm6/md8/lg12/xl16, fontSize floor-safe scale —
which is what makes every surviving `text-xs` a compliant 12px).

**Deletions — zero surviving references.** All 28 deleted files (components.json, 5 charts,
6 dashboard, 2 effects, AuroraBackdrop, Sidebar, RadialOrbital, SystemMonitor, TrustCore, 4 ui
primitives, AvatarTimeline, EventsCounter, SpectrumViz, StatBig, WallChrome) have no importers —
grep of every deleted path across app/components/lib/tests returned nothing. `gsap`,
`@react-three/drei`, `class-variance-authority` have zero references. Kept deps verified in use:
recharts (MiniSparkline only), framer-motion (FixFirst/SignInFlow/AnimatedScan/AnalysesExplorer),
three + @react-three/fiber (GlobeCore), supabase (auth), clsx/tailwind-merge (cn).
`"test": "vitest run"` present; vitest/jsdom/@testing-library/@vitejs/plugin-react correctly in
devDependencies. The pages assigned to B (scan/analyses/checks/settings) are 13–24-line wrappers
whose panels carry the whole surface — the set B needed to change is exactly the set changed
(gate B: derived, not assumed).

**Spec conformance §a–§i.** Hero (§2a): one dominant figure, exact copy rules for all three
statement branches, chips icon+text+color rendering only when count > 0, context line with the
honest incomplete-coverage caveat, whole tile → /analyses. FixFirst (§3): derive() implements the
§3.2 contract character-for-character (filter completed + analytics + block_eligible > 0 +
created_at; block DESC → created_at DESC → id DESC; slice 5; topChecks ≤2 desc; worstSev; both
empty states exact). Data Stream (§4): three real-field filters with aria-pressed, count line,
six-action TOKEN map, unknown actions render the raw string muted, shadow-block meta honest,
empty and no-match states. Bottom strip (§5): "Findings Caught" relabel, plain figure (gradient
retired from findings), heatmap real first/mid/last axis labels with T00:00:00 parse pinning,
"{n} scans so far" caption, sr-only summaries, EngineTelemetry untouched logic + 12px floor.
Globe (§6): arcs and traveling dots retired; rings per RecentTarget with deterministic tilts,
thickness ∝ files_scanned, real status colors, hover tooltip from real fields, click →
/analyses/{id}, bursts sized by real counts and rendered only for completed scans, dpr [1,2],
frameloop demand when paused/hidden, geometry disposal intact, GlobeStatic honoring the same
contract with real `<a>` links and aria-labels, WebGL check in an effect (no hydration
mismatch). Empty states (§7): every panel's zero-data copy matches the spec table, skeletons
gated behind useDelayedFlag(300) with sr-only "Loading live data…". Mobile (§8): DOM order =
stack order, globe 40vh banner <1024px, bottom strip 1/2/4 with per-breakpoint border
utilities, inputs 16px. Chrome (§9): dock 44px tabs + aria-current, palette listbox/option/
aria-selected/arrow-nav/Enter-activates/Tab-trap/Esc, boot tokens + lucide glyphs, login on
.wall-root with the exact class migration. wall.css (§10) matches §10.1–§10.5 including the
beam-sweep trigger semantics (fires only on non-null → new change, reduced-motion skip, hidden
coalescing, 750ms unmount). 12px floor (§1b): zero `text-[9/10/11px]`, zero 0.7/0.72rem font
sizes (the one 0.7rem is padding); sub-12px era is over.

**Honesty contract.** No fabricated numbers found: every figure traces to a real field through
derive(); formatNumber renders "—" for null; the globe's earth is aria-hidden decorative with
the decorative hexes commented as such. Error banner is unconditional with role="alert";
reconnect toast fires only on a real error→ok transition with role="status" + aria-live. The P2
fix is verified at all three sites: `isClean` = completed && analytics.clean
(AnalysesExplorer.tsx:29) drives the row badge (line 267: completed + 0 findings → "clean" only
when isClean, else "partial"), the clean-rate stat (line 129-133), and the Clean filter (line
50); RecentScans' badge (line 44) uses the real `RecentTarget.clean` (useWallData.ts:258) the
same way. ScanResults keeps the honest "No problems found in what was scanned" /
"{rules_ran} of {rules_total} checks ran" verdict for unclean zero-finding scans.

**QA suite.** vitest.config.ts is minimal and correct (jsdom, `@` alias, setup file, scoped
include). Tests assert behavior, not implementation: ranking contracts, aria states, filter
semantics over hostile inputs (null analytics, running scans, zero-block, unknown actions,
no-match filters), color contracts on the SVG rings, full-name (not truncated) assertions. Time
is frozen (`vi.setSystemTime` anchored to the fixture NOW) — deterministic. The `byId()`
narrowing fix is sound: `readonly FixFirstRow[]` typed, `find` + non-null assert, no structural
typing games. The next/link mock renders the same `<a href>` so href/aria assertions stay
honest. setup.ts's matchMedia polyfill is scoped and documented. I re-ran both gates myself:
tsc 0 errors, vitest 60/60 (9 files) — the reported results reproduce on the working tree.

## What I did NOT verify (named, not silent)

- `npm run build` — not re-run per brief; accepted from the Wave-3 result (success, 10 routes).
  The next integrator should let CI prove it on the committed branch.
- Launch/visual gates — I ran no servers and opened no browser (brief). The quality-floor items
  "app launched and exercised (scan run from /scan, wall updates)" and "visual check
  1440/768/390" rest on the QA wave's record, not my measurement. Confirm those were actually
  exercised before merge; contrast ratios (muted 6.7:1, faint 4.6:1, sev ≥4.5:1) are taken from
  the design doc's math, not measured.
- package-lock.json (4119 changed lines) — consistency accepted from the passing install/build;
  I did not re-verify lock integrity.

## For the next integrator

1. **The work is uncommitted on `main`.** HEAD is main tip `fa2d878` with the entire overhaul
   sitting as staged deletions + unstaged modifications. Per the operator rule (main = last
   known-good, never commit to it directly): create/check out `feat/dashboard-overhaul`, commit
   there (deletions are already staged; add the untracked new files: FixFirst.tsx, GlobeStatic.tsx,
   hooks.ts, vitest.config.ts, tests/), and treat the two IMPORTANT/ADVISORY fixes above as
   cheapest to apply before that first commit. Merge to main by PR only after the suite is green
   on the branch.
2. **Merge order vs open PRs.** #23 (fix/dashboard-deps), #24 (self-scan false positives) and
   #26 (docs audit) are ALREADY merged into this base — the branch's package.json diff is
   authored on top of them, so no conflict there. Remaining open PRs are dependabot npm bumps:
   the `@react-three/drei` and `three`/`fiber` bumps are dead on arrival (drei removed from the
   tree; GlobeCore pins three@0.169) — close them after this lands. The `next` 16.3.1 major bump
   will conflict with package.json/package-lock and likely touch the dashboard components — land
   this branch first, then re-base or recreate it. Others (framer-motion 13, tailwind-merge,
   typescript 7, types/node 26) rebase after this branch.
3. **P1 backend leak is the ship-blocker, not this branch.** placeholders.py:108 + sast.py:187,222
   (raw secret in co-located SQG003/SQG006 snippets, forwarded to the LLM via /api/crew/explain)
   needs a backend branch with the shared-redaction fix + a redaction regression test before any
   release.
4. **Version pinning note for launch copy:** the changelog should claim what is real — client-side
   derivation, honest globe, coverage-gated "clean", mobile-first cockpit — and say nothing about
   enforcement ("nothing blocks today" remains the honest state, per ChecksCatalog's own copy).
