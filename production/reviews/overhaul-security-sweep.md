# Overhaul Security Sweep — Never-Lie + Exposure (Wave 3)

Date: 2026-11-12 · Scope: current `web/` tree (overhaul waves 1–2) with backend cross-check of
`api/app/{scan,store,scans_router,api_security,settings_router}.py` and `api/app/analyzers/`.
Read-only sweep; this file is the only artifact written.

## Priority question — does any dashboard path print a raw secret?

**No, for the primary path.** The redaction happens at Finding creation, before the API, the
database, or the dashboard ever sees the value:

- `api/app/analyzers/secrets.py` — all four SQG002 builders embed only `_redact(match)` in both
  `message` and `evidence.snippet`: `_certain` (220–221), `_certain_in_test` (237–238),
  `_advisory` (307–308), `_high` (323–324). `_redact` (205–209) keeps head 4 + tail 2 chars.
- `Evidence.context_before/context_after` default to empty lists (`api/app/analyzers/base.py:32-33`)
  and no analyzer populates them (grep-verified) — there is no raw context window riding along on
  secret findings.
- `api/app/scan.py:99-147` `finding_to_dict` passes evidence through verbatim (no second
  redaction needed — the value is already masked); `api/app/store.py:310-311` persists it as-is;
  `api/app/scans_router.py` GET endpoints return it as-is.
- `web/components/findings/FindingCard.tsx:72-82` renders `ev.snippet` and context lines as
  escaped React text inside `<pre>` — no HTML interpolation anywhere, so even non-secret
  attacker-controlled repo content cannot execute (XSS-safe).

So "FindingCard renders raw evidence" is true but not a violation for SQG002: what it renders is
already `Label: xxxx...yz`. However, **other rules' evidence is NOT redacted** — finding 1 below.

---

## Findings

### [P1] Raw secret value can reach the dashboard through a co-located SQG003/SQG006 finding's evidence snippet — api/app/analyzers/placeholders.py:108, api/app/analyzers/sast.py:187,222,230-236

**Why it matters.** docs/PLAN.md rule 5 promises secret values never appear in ANY output. The
SQG002 redaction is complete, but the placeholder and SAST analyzers set
`evidence=Evidence(snippet=content.strip())` — the entire raw line. A scanned line that is both a
marker/sink and a credential assignment produces two findings: the SQG002 one with a redacted
snippet, and the SQG003/SQG006 one carrying the secret verbatim. The dashboard renders the raw
value in three places beyond the finding card: `web/components/findings/FindingCard.tsx:77`,
`web/components/findings/GroupedFindings.tsx` occurrence snippets, and the clipboard export
`web/lib/exportFindings.ts` (`buildFixPrompt` copies `f.evidence.snippet` for every finding).
Worst blast radius: `web/components/findings/FindingCard.tsx:28` POSTs the full finding to
`/api/crew/explain`, and `api/app/crew/explainer.py:38-39` forwards the evidence snippet (first
300 chars) to the third-party LLM endpoint — that is secret exfiltration off the machine.

**Concrete reproduction.** A repo containing the added line

```
password = "CorrectHorse42!"   # TODO remove before shipping
```

produces: SQG002 HIGH finding with snippet `password = Cor...42!` (redacted, correct) AND SQG003
MEDIUM finding with snippet `password = "CorrectHorse42!"   # TODO remove before shipping` (raw
secret, rendered in the dashboard, copied by "Copy for AI", forwarded to the LLM on "Explain").

**Fix.** Redact credential-shaped substrings where placeholders/sast build their snippet (share
one redaction helper with secrets.py, or strip spans matching the SQG002 patterns and the
`_ASSIGNMENT`/`_ASSIGNMENT_UNQUOTED` value groups from `content` before `Evidence(...)`).
Backend-only change; the frontend is faithful to the payload and needs no edit.

**Severity rationale.** Not P0: the primary SQG002 path is fully redacted and this needs
same-line co-location of a credential and a marker/sink. It is squarely the prioritized
secret-exposure class and breaks an absolute product promise, so it must be fixed before ship.

### [P2] "clean" is derived from `findings === 0` in AnalysesExplorer and RecentScans, contradicting the coverage-gated `clean` contract — web/components/wall/panels/AnalysesExplorer.tsx:47,126-130,264; web/components/wall/panels/RecentScans.tsx:48-49

**Why it matters.** The backend defines `clean` as "every check ran, found nothing, AND every
file was read" (`api/app/scan.py:158-160` docstring; `web/lib/types.ts` Analytics.clean: "NOT the
same as `total_findings === 0`"). A completed scan with zero findings but errored/timed-out
checks (analytics.clean === false) shows the word "clean" in the explorer filter, the summary
clean-rate, the row badge, and the RecentScans badge. The dashboard Hero
(`web/app/dashboard/page.tsx:56-78`) and the ScanResults verdict
(`web/components/wall/panels/ScanResults.tsx:170-192`) use the real flag correctly, so the lie
is only in these two views — but it is precisely the "zero findings ≠ clean" confusion the
coverage system was built to kill.

**Fix.** Use `s.analytics?.clean` (AnalysesExplorer rows/stat; `RecentTarget.clean` already
exists in `web/lib/useWallData.ts:48` — RecentScans just doesn't use it for the badge). Under-
covered scans should read `0 findings` / "inconclusive", not "clean".

### [P3] Audit-feed failure silently renders as an empty stream — web/lib/useWallData.ts:330; web/components/wall/DataStreamFeed.tsx:110

`Promise.all([listScans(), listAudit().catch(() => [])])` swallows audit-endpoint failures. If
only the audit route is down, the Data Stream shows "Awaiting events — run a scan to populate
the stream" while events exist; the dashboard error banner never fires (it keys off the
listScans rejection only). An outage must not read as "no activity". Surface the audit failure
(e.g. a muted inline notice) or include it in the error state.

### [P3] AnalysesExplorer poll failure after first load leaves stale data with no indicator — web/components/wall/panels/AnalysesExplorer.tsx:155

`if (error && !scans)` renders the error only before the first successful load; afterwards
`setError` is set but never displayed, so a dead API keeps showing the last list next to a live
"scanning…" pulse. The dashboard page handles this correctly (`role="alert"` banner,
`page.tsx:206-214`); the explorer should show a muted staleness notice too.

### [P3] trustStatus / hasRecentFailure are computed but never rendered — web/lib/useWallData.ts:93-94,278,307

The WallData contract advertises a green/red trust signal with an explicit "do not fabricate the
yellow tier" note, but no component consumes it. Not a lie (nothing renders a fake-green badge),
but it is dead honesty: wire it to a visible indicator or drop the fields so the contract
doesn't imply a status the UI doesn't show.

### [P3] Dashboard has no mechanism to send the API key; keyed deployments fail closed with opaque 401s — web/lib/api.ts (all fetches); api/app/api_security.py:24-30

`require_api_key` is enforced server-side on every endpoint the client calls, including PATCH
/api/settings (`api/app/settings_router.py:16,22`) — there is no client-side bypass, which is
the security-positive direction. But `web/lib/api.ts` never attaches `X-API-Key`, so the moment
an operator sets `API_KEY`, every dashboard call 401s and the UI can only show the generic error
banner. Demo mode depends on open mode (`API_KEY` empty). Add a documented client key path (or
explicitly state the dashboard is open-mode-only) so a keyed deployment doesn't look broken.

### [P3] Stored scan.error embeds raw exception text — api/app/scans_router.py:84; api/app/store.py:260-272; rendered raw at web/components/wall/panels/ScanConsole.tsx:155

`_enqueue_or_fail` writes `f"could not be queued for scanning: {exc}"` into the scan row, and
ScanConsole prints it under "Details:". redis-py exception messages do not normally echo the
connection URL, but a malformed `REDIS_URL` ValueError could carry it (a passworded URL would
then sit in the DB, the audit trail, and the dashboard). Scrub connection-string-looking
substrings from stored error text as cheap defense-in-depth.

### [P3] `_redact` deliberately reveals 6 characters of a secret — api/app/analyzers/secrets.py:205-209

Head 4 + tail 2 is standard secret-scanner practice and cannot reconstruct a 36+ char token, but
it is a policy choice worth one line in the docs: the dashboard intentionally shows a
truncated prefix, not an accidental leak. Keep as-is; document it.

### [P3] Supply-chain notes — web/package.json

- Removed deps verified unreferenced: grep across `app/ components/ lib/ tests/` finds zero hits
  for `gsap`, `@react-three/drei`, `class-variance-authority`/`cva`. Clean prune.
- Kept deps verified used: `recharts` only by `components/charts/MiniSparkline.tsx` (consumed by
  FindingsTrend on the wall); `@react-three/fiber` + `three` by `GlobeCore.tsx`;
  `@supabase/supabase-js` by `lib/auth.ts` + auth components; `clsx` + `tailwind-merge` by
  `lib/utils.ts cn()`.
- `vitest`, `jsdom`, `@testing-library/react`, `@vitejs/plugin-react` are devDependencies only
  and wired via `vitest.config.ts` / the `test` script — never in the client bundle;
  `next.config.mjs` `output: "standalone"` additionally excludes devDeps from the runtime image.
- Minor: `@types/three` sits in `dependencies` though it is types-only (erased at build; ships
  nothing to the browser). Move to devDependencies for correctness of the production install.

### [P3] Comment drift — web/lib/types.ts ScanProgress `total: number // 6`

The backend emits 8 analyzers (`api/app/scan.py:245-254`) plus reporting. Only a comment lie;
the runtime handles it (`AnimatedScan.tsx:79` falls back to the raw phase string for
unmapped phases like `typosquat`/`simplify` — honest, no invented label).

---

## Verified-clean checklist

1. **Secret exposure (PRIORITY).** SQG002 redaction complete at source (see header); no
   `dangerouslySetInnerHTML` / `innerHTML` / `eval` / `document.write` anywhere in `web/`;
   evidence, snippets, audit details, tooltips, and group occurrences all render as escaped
   React text; external links carry `rel="noopener noreferrer"` (FindingCard.tsx:94,106); no
   `window.open`/`location` sinks; CWE links are constructed against a fixed host. Residual risk
   is the P1 co-location gap only.
2. **Env / demo mode.** `web/.env.local` is untracked (`git check-ignore` → `web/.gitignore:3`),
   keys blank, byte-identical in shape to `.env.example`; no `NEXT_PUBLIC_*` variable carries a
   secret value (`NEXT_PUBLIC_API_URL` defaults to `localhost:8000` only);
   `web/lib/auth.ts:15` builds no client and no fallback key when the Supabase vars are blank —
   demo mode cannot leak or render a key. Git-history secret sweep was out of scope per the
   brief's "no git" hard rule; recommend a one-off `gitleaks`/history scan as separate work.
3. **No fabricated data.** Every number on the wall derives from real API fields via
   `derive()` (`web/lib/useWallData.ts:141-310`, pure, exported for QA): hero figures,
   FixFirst ranking (block_eligible desc → created_at desc → id desc, top 5), byCheck/topFiles,
   heatmap buckets, severity series, EngineTelemetry queue/avg/throughput. `formatNumber`
   renders "—" for null rather than 0-as-fact. FixFirst "All clear" and heatmap/empty states
   state what is actually absent. The one clean-vs-findings conflation is P2 above.
   `AnimatedScan` uses the real phase index (no invented % or ETA — the mockup's "EST. TIME"
   was deliberately dropped).
4. **Honest globe contract.** `GlobeCore.tsx` docstring and implementation agree: earth =
   decorative brand backdrop sampled from a public-domain NASA map (`aria-hidden`), data layers
   are one orbit ring per recent scan (thickness ∝ real `files_scanned`, color = real status,
   click → `/analyses/{id}`), bursts/beams sized by real finding counts, positions on a
   Fibonacci sphere — no data claims geography, and the point-to-point "traffic arcs" are
   retired. `GlobeStatic.tsx` honors the same color/thickness/label contract with real `<a>`
   links. Legends state the actual encoding ("Orbits = last N scans · thickness = files scanned
   · colour = status").
5. **Honest states.** Error banner is unconditional on `error` (`page.tsx:206-214`,
   `role="alert"`); reconnect toast fires only on a real error→ok transition
   (`page.tsx:148-156,298-307`); skeleton mounts only after a 300ms delayed loading flag with an
   sr-only "Loading live data…" (`page.tsx:115-129,200`) and never fakes success; EngineTelemetry
   online/offline comes from real reachability (`useWallData.ts:354`) and reports no fabricated
   CPU/RAM gauges (`BottomStats.tsx:47-75`); ScanConsole timeout message is honest
   ("Still running in the background…"); ScanResults verdict distinguishes "All clear" from "No
   problems found in what was scanned" with per-rule coverage receipts
   (`CoveragePanel.tsx`); skipped/suppressed banners state that unread files can hide findings.
6. **Client-side trust.** Settings writes go through PATCH /api/settings with server-side
   `require_api_key` + rate limit and boundary validation (`settings_router.py:22-51`);
   `blocked_rules` filtered against server `RULE_IDS` again in `store.update_settings`
   (`store.py:452`); the client's rule list (`web/lib/checks.ts`) matches the server set exactly
   — SQG008 absent on both sides so the UI can never offer a check that never runs. Settings
   copy was de-lied (retention explicitly says "nothing is deleted yet"). The P3 API-key note
   above is the only trust-surface gap, and it fails closed.
7. **XSS.** Covered under 1 — zero raw-HTML sinks in the changed files; all interpolation is
   React-escaped text.

---

## Verdict

**FINDINGS REQUIRE ACTION** — one P1 (backend co-location snippet leak, fix in
`placeholders.py`/`sast.py` before ship), one P2 ("clean" overstated in AnalysesExplorer /
RecentScans), rest are hardening notes. The dashboard rendering layer itself is clean: no XSS
sinks, no fabricated data, no env-key leakage, honest states throughout.
