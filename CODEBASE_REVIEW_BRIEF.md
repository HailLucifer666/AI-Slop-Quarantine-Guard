# AI Slop Quarantine Guard — Codebase Review Brief

> A complete, self-contained summary of the current build, written to be fed to another AI for
> an architecture/quality/false-positive review. It states what the app **is**, what it **can**
> do, what it **cannot** do, the exact detection logic of every check (with code), and an honest
> ledger of known gaps, false-positive risks, and dead code. Where this brief and the docs in
> `docs/` disagree, **the code is the source of truth** — this brief is generated from the code.

---

## 1. What this app is

**AI Slop Quarantine Guard** is a pre-release **quality + security gate** for code, aimed at a
non-technical "vibe coder" audience (people who build apps with AI but can't read code). It runs
every machine-possible check for AI "slop" — hallucinated packages, leaked secrets,
known-vulnerable dependencies, risky licenses, dangerous code patterns, placeholder/stub code —
and reports findings in plain English.

It has **two layers that must never be mixed**:

- **The Guard** — a deterministic engine of 6 analyzers (`SQG001`–`SQG006`). Blocks only on
  *provable facts*. The defensible core.
- **The Crew** — an advisory LLM explainer that translates a finding into plain English. It is
  **read-only**: never changes a verdict, never claims code was AI-written, degrades to "unavailable"
  on any failure.

**The product promise (the moat):** *"We run every known check, catch what those checks can catch,
and we never lie to you about a fact."* A finding is only **CERTAIN / block-eligible** when it is
**reproducible** — a clean 404 from a *reachable* registry, a structurally-distinctive secret with a
real key body. Any registry/tool **outage downgrades to advisory; it never blocks** (the fail-safe).
This honesty rule outranks feature velocity.

**Two delivery surfaces, one engine:**
1. **PR gate** — a GitHub App webhook analyzes a pull-request diff and writes a GitHub Check Run.
2. **Whole-repo scan** — a pasted repo URL / uploaded zip / local folder is ingested and scanned;
   results feed an "Aurora-on-Black" Next.js dashboard.

**Current status:** Phases 1–4 complete (webhook → worker+auth → 6 analyzers → Check-Run output,
**label-only**). Whole-repo scanner + dashboard added alongside. Crew explainer + settings page exist.
**Real blocking/enforcement is NOT implemented** (Phase 9, gated behind a measured <1% false-positive
rate).

---

## 2. Tech stack & layout

- **Backend:** Python 3.12 · FastAPI (async) · `httpx` · SQLAlchemy 2.0 (async) · SQLite (→ Postgres
  planned) · plain Redis list queue + a standalone `worker.py` consumer. No Trivy/Semgrep/Syft/Gitleaks
  binaries — every analyzer is pure-Python regex or a direct HTTP call to a public registry/API.
- **Frontend:** Next.js 15 · Tailwind · shadcn/ui · three.js. Root redirects to `/dashboard`.
- **Auth:** GitHub App (JWT → installation token) for the PR path.
- **LLM (Crew):** OpenAI-compatible endpoint, default NVIDIA NIM `minimaxai/minimax-m3`.

```
api/app/
  main.py            # FastAPI app: /webhooks/github, /healthz, mounts 4 routers
  config.py          # pydantic-settings, env-driven
  queue.py           # Redis: dedupe (SET NX EX), webhook + scan enqueue (LPUSH)
  worker.py          # dual-queue consumer: analyze_pr() + handle_scan_job()
  diff.py            # unified-diff parser -> (path, new_line, added_content)
  synthetic_diff.py  # whole-repo -> all-added diff so analyzers run unchanged
  ingest.py          # clone / zip / walk a codebase into {path: content}, with caps + SSRF guard
  manifests.py       # parse requirements.txt / pyproject.toml / package.json / Cargo.toml -> names
  registries.py      # PyPI / npm / crates existence check -> EXISTS | MISSING | UNKNOWN
  scan.py            # whole-repo orchestrator: run all 6 analyzers + aggregate analytics
  checks.py          # GitHub Check-Run conclusion + plain-English summary + annotations
  store.py           # async persistence over scans / audit_log / app_settings
  github_auth.py     # App JWT -> installation token
  github_client.py   # fetch PR diff / file content, create/update check runs
  analyzers/
    base.py          # Finding / Evidence / Confidence model (the universal currency)
    dependencies.py  # SQG001 hallucinated dependency
    secrets.py       # SQG002 leaked secret
    placeholders.py  # SQG003 placeholder / stub code
    vulns.py         # SQG004 known-vulnerable dependency (OSV.dev)
    licenses.py      # SQG005 risky (copyleft) license
    sast.py          # SQG006 dangerous-API sink
  crew/explainer.py  # advisory LLM explainer
  db/models.py       # SQLAlchemy models
  *_router.py        # scans / crew / audit / settings APIs
web/                 # Next.js 15 dashboard (Aurora-on-Black)
```

---

## 3. Data flow

**PR gate** (`worker.py::analyze_pr`):
```
GitHub webhook --HMAC verify--> dedupe (Redis) --> enqueue raw delivery --> 202 (fast ACK)
worker brpop --> get installation token --> create "in-progress" Check Run
  --> fetch PR diff --> run 6 analyzers over the diff
  --> determine_conclusion (success | action_required)  # NEVER "failure" yet
  --> update Check Run: plain-English summary + <=50 inline annotations
```

**Whole-repo scan** (`worker.py::handle_scan_job` -> `scan.py::run_scan`):
```
POST /api/scans (url | local | zip) --> create scan row (queued) --> enqueue --> 202 {scan_id}
worker brpop --> ingest_codebase() -> {path: content} + skipped[]
  --> build_synthetic_diff(): every line tagged as "added"
  --> run the SAME 6 analyzers, in fixed order, with progress callbacks
  --> aggregate() -> analytics --> persist findings+analytics JSON on the scan row
dashboard polls GET /api/scans/{id}
```

The key trick: the analyzers only know how to read `parse_diff()` output (a stream of *added*
lines). A whole-repo scan fakes an all-added diff so the exact same code runs over a full codebase.

```python
# synthetic_diff.py — make every line look "added"
def build_synthetic_diff(files: Dict[str, str]) -> str:
    chunks = []
    for path, content in files.items():
        lines = content.splitlines()
        if not lines:
            continue
        body = "".join(f"+{line}\n" for line in lines)
        chunks.append(f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}")
    return "".join(chunks)
```

---

## 4. The universal currency: `Finding`

Every analyzer returns a list of `Finding`. Two fields carry the whole product promise:
`confidence` (CERTAIN / HIGH / MEDIUM) and `block_eligible` (whether this finding *could* ever
gate a merge — only ever `True` for provable facts).

```python
# analyzers/base.py
class Confidence(str, Enum):
    CERTAIN = "CERTAIN"   # provable / reproducible
    HIGH    = "HIGH"      # strong signal, FP-prone -> advisory
    MEDIUM  = "MEDIUM"    # worth a look -> advisory

@dataclass
class Finding:
    category: str          # dependency | secret | placeholder | vulnerability | license | sast
    confidence: Confidence
    block_eligible: bool   # True ONLY on CERTAIN provable findings
    file_path: str
    line_start: int
    line_end: int
    message: str
    evidence: Evidence     # snippet (+ optional context)
    tool: str              # registry:<eco> | regex | osv | ...
    rule_id: str           # SQG001..SQG006
    fix_suggestion: Optional[str] = None
```

**Check-Run output is label-only today** (`checks.py`):
```python
def determine_conclusion(findings: List[Finding]) -> str:
    # Phase 4: success when clean, else action_required (orange). NEVER "failure".
    return "action_required" if findings else "success"
```
`block_eligible` is computed and persisted now so that turning on real blocking later is a config
change, not a rewrite. Annotations are capped at 50 (GitHub's limit), most-severe first.

---

## 5. The 6 analyzers — exact detection logic

### SQG001 — Hallucinated / non-existent dependency  *(the defensible core)*

**Catches:** a package name added in a PR's manifest that returns a clean **404** from its real
registry. **Confidence model:** registry 404 → `CERTAIN` + `block_eligible=True`; registry
unreachable → `HIGH` advisory (never blocks). Names are extracted by a **real parser**
(`tomllib`/`json`/requirements), and local/git/url/workspace specs are filtered out upstream
(they can't be registry-checked, so flagging them would be a false positive).

```python
# analyzers/dependencies.py (core loop, trimmed)
for path, added in added_by_file.items():
    ecosystem = manifest_ecosystem(path)            # requirements.txt/pyproject/package.json/Cargo.toml
    if ecosystem is None:
        continue
    content = await fetch_file(path)
    if not content:
        continue                                    # can't parse -> stay silent (protects zero-FP)
    for name in extract_dependency_names(path, content):
        line = _name_present(name, added)           # only if the name is on an ADDED line
        if line is None:
            continue
        result = await exists_fn(ecosystem, name, client)
        if result is Existence.MISSING:             # clean 404 from a reachable registry
            findings.append(_missing_finding(...))  # CERTAIN, block_eligible=True
        elif result is Existence.UNKNOWN:           # outage/timeout/429 after retries
            findings.append(_unknown_finding(...))  # HIGH advisory, block_eligible=False
```

```python
# registries.py — the three-outcome existence check (fail-safe by design)
async def check_exists(ecosystem, name, client) -> Existence:
    url = _registry_url(ecosystem, name)            # pypi / npm / crates
    if url is None:
        return Existence.UNKNOWN
    for attempt in range(_RETRIES + 1):
        try:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True)
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1)); continue
        if resp.status_code == 200: return Existence.EXISTS
        if resp.status_code == 404: return Existence.MISSING
        await asyncio.sleep(0.5 * (attempt + 1))    # 429/5xx -> retry
    return Existence.UNKNOWN                         # never assert MISSING on an outage
```

### SQG002 — Leaked secret  *(offline regex, no external tool)*

**Catches:** credential material on added lines, in two tiers. **CERTAIN/block-eligible:**
structurally-distinctive tokens (AWS `AKIA…`, GitHub `ghp_…`, Stripe `sk_live_…`, Slack `xox…`,
Google `AIza…`, PEM private-key blocks). **HIGH/advisory:** generic `secret = "…"` assignments.
Heavy FP-suppression: an allowlist (`example`, `your_`, `os.getenv`, `process.env`, `${`, …),
**path downgrades** (a distinctive token in a `tests/`/`examples/`/`docs/` path is surfaced but
*never block-eligible*), and a **PEM body look-ahead** (a `BEGIN PRIVATE KEY` header with no base64
body following it is treated as illustrative, not a real key). Secret values are always redacted.

```python
# analyzers/secrets.py (decision core, trimmed)
for label, pattern in _CERTAIN_PATTERNS:
    m = pattern.search(content)
    if not m:
        continue
    if label == "private key block" and not _has_key_body(added, idx):
        finding = _advisory(...)            # header only, no key body -> advisory
    elif in_test:
        finding = _certain_in_test(...)     # tests/fixtures path -> HIGH, not blocked
    elif in_example:
        finding = _advisory(...)            # docs/examples/templates -> advisory
    elif _looks_placeholder(content):
        finding = _advisory(...)            # "...", single-line PEM -> advisory
    else:
        finding = _certain(...)             # CERTAIN, block_eligible=True
    break                                   # one finding per line, CERTAIN wins
# fallback generic assignment: `name(secret|token|api_key...) = "8+ chars"` -> HIGH advisory
```

### SQG003 — Placeholder / incomplete code  *(advisory only)*

**Catches:** `TODO/FIXME/XXX/HACK`, `NotImplementedError` / `throw new Error("not implemented")`,
ellipsis-only bodies (`^\s*\.\.\.\s*$`), and "your code here" / "implement this" prose. **Always
`MEDIUM`, never block-eligible** — a TODO can be intentional. Doc files skipped; `# noqa` /
`# type: ignore` / `# pragma: no cover` allowlisted. Regex MVP; AST-aware empty-body detection is
deferred.

### SQG004 — Known-vulnerable dependency  *(OSV.dev API)*

**Catches:** an **exactly-pinned** version, introduced on an added line, that OSV.dev reports as
vulnerable. **Always `HIGH`, never block-eligible** — a CVE's presence ≠ exploitability. **Fail-safe:**
OSV unreachable/timeout/429 → `None` → the dep is silently skipped. **Scope (MVP):** only exact pins
are checkable — pip `name==1.2.3` and npm exact semver. Range/caret specs (`^1.2`, `>=1.0`, Cargo
bare versions, pyproject ranges) are **skipped** because the installed version is unknown without a
real resolver.

```python
# analyzers/vulns.py (trimmed)
for ecosystem, name, version in _pinned_deps(path, content):   # only EXACT pins
    line = _find_line(name, version, added)
    if line is None:
        continue
    vulns = await query(ecosystem, name, version, client)       # OSV.dev
    if vulns:                                                    # None or [] -> no finding
        findings.append(_vuln_finding(name, version, vulns, path, line))  # HIGH advisory
```

### SQG005 — Risky (copyleft) license  *(registry metadata)*

**Catches:** a dependency whose registry license metadata matches copyleft families
(GPL/AGPL/LGPL/SSPL). **Always `MEDIUM`, never block-eligible** — license compatibility is a legal
judgement. **Scope:** PyPI + npm only. Notable FP-guard: PyPI's free-text `license` field is often
the *entire* license document (e.g. pandas/scipy paste full BSD text that merely *mentions* "GPL"),
so the analyzer only trusts **structured** signals — trove `classifiers`, the SPDX
`license_expression`, and a *short single-line* `license` field.

```python
# analyzers/licenses.py — avoid the full-text-license false positive
def _pypi_license_label(info: dict) -> str:
    classifiers = " ".join(c for c in info.get("classifiers", []) if "License" in c)
    raw = (info.get("license") or "").strip()
    short_license = raw if (len(raw) <= 80 and "\n" not in raw) else ""   # ignore full body
    expr = info.get("license_expression") or ""
    return f"{short_license} {expr} {classifiers}".strip()
```

### SQG006 — Dangerous-API sink  *(lightweight SAST, regex)*

**Catches:** a curated, high-signal pattern set over added lines — a mini-Bandit, not Semgrep.
Python: `eval(`/`exec(` (builtins only via negative look-behind), `os.system(`, `shell=True`,
`pickle.load(s)`, `yaml.load(` without `SafeLoader`, `hashlib.md5/sha1`. JS/TS: `eval(`,
`child_process.exec`, `dangerouslySetInnerHTML`, `.innerHTML =`, `document.write(`. **Always
`HIGH`/`MEDIUM`, never block-eligible** — static sink detection has irreducible FPs. Language-gated
by extension, doc files skipped, `# nosec`/`// nosec`/`# noqa` honored, and **comment-only lines
skipped** so a sink named in prose doesn't fire.

---

## 6. Persistence & API

- **`scans` table** stores a whole-repo scan; findings + analytics are stored as **JSON text on the
  row** for the MVP (normalized tables are Phase 5). `progress` holds live phase while running.
- **`audit_log`** records every scan lifecycle transition + settings change (tamper-evident trail),
  written in the **same transaction** as the state change.
- **`app_settings`** (single row id=1) stores `block_mode`, `blocked_rules`, `retention_days`.
- **API:** `POST /api/scans` (url/local/zip), `GET /api/scans`, `GET /api/scans/{id}`, plus crew /
  audit / settings routers. Webhook: `POST /webhooks/github`, health: `GET /healthz`.

Input is validated at the boundary: `validate_clone_url` enforces **https-only + an allowlist of
public forge hosts** (SSRF guard) and rejects credentials-in-URL; uploads are size-capped; local-dir
scans are dev-only. Ingest applies hard caps (5000 files, 50 MB total, 1 MB/file), skips binary &
vendored dirs, and reads zip entries **in memory** (no extraction → no zip-slip).

---

## 7. What it CAN do (capabilities)

- Detect **provably non-existent** packages (pip / npm / crates) and block-eligibly flag them on a
  clean 404 — the core anti-hallucination check.
- Detect distinctive **leaked secrets** with redaction and aggressive FP-downgrade in test/example paths.
- Flag **known-vulnerable** exactly-pinned deps (pip/npm) via OSV.dev — advisory.
- Flag **copyleft licenses** (pip/npm) via registry metadata — advisory.
- Flag **dangerous-API sinks** and **placeholder/stub code** via curated regex — advisory.
- Run the identical engine over a **PR diff** or a **whole repo** (URL/zip/local).
- Produce **plain-English** Check-Run summaries + inline annotations, and dashboard analytics.
- **Fail safe**: any registry/tool/LLM outage degrades to advisory or "unavailable" — it never
  emits a false block and never silently drops a scan (failures are recorded with a reason).
- Optional **LLM explanations** per finding (advisory, read-only, graceful-degrading).

## 8. What it CANNOT do (limitations — be explicit)

- **No enforcement / blocking yet.** `determine_conclusion` only returns `success` /
  `action_required`. `block_mode` & `blocked_rules` are persisted but **not read by the engine**
  (see §9). There is no merge gate today.
- **No lockfile / transitive analysis.** Only top-level manifest declarations are parsed; no
  `package-lock.json`, `poetry.lock`, `yarn.lock`, `Cargo.lock`; no transitive dependency tree.
- **Narrow ecosystem coverage.** Existence: pip/npm/crates. Vulns + licenses: **pip/npm only**.
  No Go, Ruby, Java/Maven, PHP/Composer, .NET, Cargo vulns, etc.
- **No range-version vuln/license resolution** — caret/range/bare specs are skipped (no resolver).
- **No typosquatting / malicious-package / install-script detection** — a package that *exists* but
  is a typosquat or malware is not caught.
- **Regex-only SAST & placeholders** — no AST, no taint analysis, no data-flow; no real Semgrep/Bandit.
- **No entropy-based secret detection** — only distinctive known token shapes + a generic assignment
  rule; a high-entropy custom secret with no recognizable prefix is missed.
- **No deduplication across rules**, no severity merging, no SARIF/standard export.
- **Storage is MVP**: SQLite, JSON-on-row; the normalized `Analysis`/`Finding` tables exist but are
  **not used** by the scan path.
- **No auth/rate-limiting on the scan API** (`/api/scans` is open); intended for a trusted/dev context now.
- **Binary, config, IaC, container, and Dockerfile checks are absent** (backlog).

---

## 9. Known gaps, dead code & false-positive risks  *(the review target)*

This is the honest engineering ledger — the most useful section for a reviewer. Each item is
grounded in the code above.

**Dead / unwired:**
1. **`disabled_analyzers` kill-switch is dead.** Defined in `config.py` (and `.env`/docs) but **read
   by no analyzer, worker, or scan path** (verified by search). The advertised per-rule kill-switch
   does nothing.
2. **Enforcement is unwired.** `block_mode` / `blocked_rules` are persisted via `settings_router` /
   `store.py` and shown in the dashboard, but **no code in `worker.py`/`scan.py`/`checks.py` reads
   them**. `block_eligible` is carried but never consulted. (Expected — Phase 9 — but a reviewer
   should know the gate is inert.)
3. **Stub leftovers:** `queue.py::enqueue_analysis_job` / `get_job_status` are `pass`-body stubs
   superseded by the real Redis queue. `db/models.py::Analysis` & `Finding` tables are unused by the
   scan path.
4. **Docs drift:** docs mention `arq` for the queue; the real implementation is a plain Redis list
   + `brpop` loop. `pydantic` `class Config` (v1 style) is used with `pydantic-settings` v2.

**False-positive / over-catching risks** (what the user flagged — "catching things it shouldn't"):
5. **SQG003 (placeholders) fires on substring matches in any code line** — `TODO`/`FIXME`/`HACK`
   inside a string literal, a variable named `hack_*`, or legitimate prose in a code file all match.
   Advisory, but noisy. No comment/scope awareness beyond doc-file skipping.
6. **SQG006 (SAST) regex has classic FPs** — `shell=True` anywhere (incl. a dict key or a string),
   `.innerHTML =` on a trusted constant, `eval(` shadowed by a local, `yaml.load` already wrapped
   safely on a prior line. Advisory, but will over-report on real codebases.
7. **SQG002 generic assignment tier** (`name(secret|token|...) = "8+ chars"`) will fire on config
   defaults, sample values, and non-secret strings that happen to be assigned to a credential-named
   variable outside an allowlisted/test path. Advisory.
8. **SQG001 line-binding is a token regex** (`_name_present`) — it binds a parsed dependency name to
   the first added line containing that token. The **block decision is still safe** (it depends only
   on a registry 404, which is provable), but the *reported line/snippet* can be mis-attributed if
   the name appears in a comment or unrelated string in the manifest.
9. **Whole-repo scan amplifies advisory noise**: because every line is "added", advisory analyzers
   (SQG003/SQG006/SQG002-generic) report on the entire codebase at once. Real-world repos will
   produce large advisory counts; the dashboard needs strong grouping/prioritization (or the rules
   need tightening) so the signal isn't buried.

**False-negative / coverage gaps** (where it stays silent):
10. **No typosquat detection** — `reqeusts`, `python-dateutil` look-alikes that *exist* pass clean.
11. **Vuln/license checks skip every non-exact version** and every ecosystem beyond pip/npm — a repo
    using caret ranges (typical npm) gets little SQG004 coverage.
12. **Secrets without a known prefix** (custom API tokens, DB URLs with embedded passwords not
    matching the assignment regex) are missed — no entropy fallback.

---

## 10. Suggested questions for the reviewing AI

1. Is the **CERTAIN/block-eligible** boundary actually airtight? Can any analyzer ever emit
   `block_eligible=True` on something not strictly reproducible? (Audit every `block_eligible=True`
   construction against the "never lie about a fact" promise.)
2. How should the **advisory noise** from SQG003/SQG006/SQG002-generic be reduced without losing
   recall — tighter patterns, scope/comment awareness, AST, or post-hoc grouping/dedup?
3. What is the **highest-leverage coverage gap** to close first: typosquatting (anti-hallucination
   adjacency), lockfile/transitive parsing, range-version vuln resolution, or more ecosystems?
4. Is the **synthetic-all-added-diff** reuse of the PR analyzers sound for whole-repo scanning, or
   does it create subtle semantic mismatches (e.g. look-ahead/window logic in `secrets.py`)?
5. Should `disabled_analyzers` and `block_mode`/`blocked_rules` be **wired now** (even read-only/dry-run)
   to validate the Phase 9 gate before it's trusted with real blocking?
6. Where would a real **Semgrep/Bandit/Gitleaks/Trivy/Syft** integration replace the regex MVPs with
   the least disruption to the `Finding` contract?
7. Production-readiness: auth/rate-limiting on `/api/scans`, SQLite→Postgres, JSON-on-row →
   normalized tables, and idempotency/retry semantics of the single `worker.py` consumer.

---

*Generated from the code (not the docs). Backend entrypoints to read first if you want to verify:
`api/app/worker.py`, `api/app/scan.py`, `api/app/checks.py`, and `api/app/analyzers/*.py`.*
