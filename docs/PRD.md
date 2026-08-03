# Product Requirements Document (PRD)
## PR Quality & Security Gate — Working Title (Final Name TBD)

> **Naming note:** Internal codename is "Slop Quarantine Guard." This is pejorative toward users who build with AI assistance — it must not appear on any customer-facing surface. All external language uses neutral terms: "PR Quality & Security Gate" or similar. Final name to be decided before public launch.

---

## 1. Problem & Persona

### Who this is for

**The "vibe coder" founder.** Someone who builds real software using AI coding tools (like Cursor, GitHub Copilot, or Claude) but cannot read or fully verify the code that gets generated. They ship features fast but have a nagging fear: *What if the AI hallucinated a package that doesn't exist? What if it accidentally pasted in a secret? What if it included a known security hole I'd never notice?*

They can't hire a security team. They can't do a manual code review. They need an automated safety net that runs the same checks the best tech companies run — before their code goes live.

### The core problem

AI-generated code introduces a new category of risk that traditional tools weren't designed to catch:

- **Hallucinated (fake) packages:** AI invents package names that don't exist. Attackers register those names with malicious code. Your app installs the attacker's code. This is called "slopsquatting" or "dependency confusion."
- **Accidentally committed secrets:** API keys, passwords, tokens pasted or generated inline and never removed.
- **Known security holes:** Dependencies with published vulnerabilities (CVEs — known, cataloged security flaws) that the AI didn't know about or didn't flag.
- **Incomplete code:** `TODO` stubs, empty functions, placeholder logic that looks complete but does nothing (or crashes in production).
- **Risky licenses:** Open-source libraries whose legal terms conflict with selling your product commercially.

The problem is not that AI is bad. The problem is that **there is no automated pre-release gate** that catches all of these things, explains them in plain English, and stops dangerous code from being merged.

---

## 2. The Honest Promise (This Is the Moat)

> **"We run every known check the best companies run, and we catch everything those checks can catch — and we never lie to you about a fact."**

This is not a claim of being "hackproof." No product can promise that — not even Google's security team. What we promise is:

1. We run the same automated checks that elite engineering teams run (package existence verification, secret scanning, vulnerability databases, license analysis, code completeness checks).
2. When we flag something, it is a verifiable fact — not a guess, not an AI opinion, not a statistical inference.
3. When we are uncertain, we say so — and we downgrade from "block" to "advisory."
4. We never claim to detect that code was "written by AI." We make no such assertion. We check facts.

**Trust through verifiable truth is the entire competitive advantage.**

---

## 3. Two Layers — Never Mixed

The product has two distinct layers that serve different purposes. These must never be confused or combined.

### Layer 1: The Guard (Deterministic Engine)

- Runs proven, deterministic tools (tools that always give the same answer for the same input).
- **Blocks only on proven facts** — things that can be independently verified (a package that returns a confirmed "does not exist" from the registry, a secret that matches a known format with checksum confirmation, a dependency version that matches a known vulnerability database entry).
- Never guesses. Never uses AI to decide whether to block.
- If a tool fails, times out, or is unavailable: it degrades to advisory, never blocks. The fail-safe is always "let through with a warning," never "block because we couldn't check."

### Layer 2: The Crew (AI Explainer/Advisor)

- Takes the Guard's findings and translates them into plain English.
- Explains what the problem is, why it matters, and how to fix it — with code examples.
- **Advisory only.** The Crew never blocks a pull request on its own. It never changes a finding's conclusion. It never asserts that code was written by AI.
- Built in Phase 7 (after all checks are working and the dashboard is live).

These two layers talk to each other in only one direction: Guard findings flow into the Crew for explanation. The Crew never flows back to influence the Guard.

---

## 4. Checks Catalog (What Gets Checked)

Each check has a permanent ID (a "Rule ID") so you can reference, suppress, or configure it consistently. Suppressing a rule (ignoring it for a specific file or repository) uses the ID — e.g., `ignore: SQG005`.

| Rule ID | What It Checks | How Confident | Blocks by Default? |
|---------|----------------|---------------|-------------------|
| **SQG001** | Fake / hallucinated package (does the package actually exist in the public registry?) | CERTAIN — if the registry responds with a clean "not found" | Opt-in (Phase 9) |
| **SQG002** | Leaked secret or API key in code | CERTAIN — if format + checksum match a known secret pattern | Opt-in (Phase 9) |
| **SQG003** | Placeholder / incomplete code (`TODO`, empty function bodies, `throw "not implemented"`) | MEDIUM | Never blocks |
| **SQG004** | Known-vulnerable dependency (CVE match — a published security flaw in a package version you're using) | HIGH — the match is factual, but "your code is exploitable" requires deeper analysis we don't do yet | Never blocks (advisory) |
| **SQG005** | Risky or incompatible license (e.g., GPL in a commercial product) | HIGH | Never blocks |
| **SQG006** | Outdated dependency | HIGH | Never blocks |
| **SQG007** | Typosquatted dependency name (`reqeusts` for `requests`) | HIGH — a suspicion about intent, never a provable fact | Always on, advisory only, never blocks |
| **SQG008** | AI scratchpad committed by accident (`<thinking>` blocks, plan dumps) | HIGH — but narrow regex, text/markdown files only | **Not implemented** (was mis-numbered SQG007; see CHECKS_CATALOG.md) |
| **SQG009** | Avoidable complexity — several lines of code that one equivalent line replaces | MEDIUM — the shorter form is derived from the syntax tree and shown verbatim, but taking it is a judgement | Never blocks (advisory) |

**Confidence levels explained:**
- **CERTAIN** = a reproducible, independently verifiable fact. Eligible to block (when user opts in).
- **HIGH** = strong evidence, but context could change the conclusion. Advisory only.
- **MEDIUM** = a signal worth noting; context matters a lot. Advisory only.

**The fail-safe rule:** If any checker cannot reach the internet, times out, gets rate-limited, or crashes — that check degrades to advisory. It never blocks when it's uncertain. This is the "never lie" promise in action.

---

## 5. How It Works (User Journey)

1. **Install** the app on a GitHub repository. One click. No code changes needed.
2. **Open a pull request** — whether you wrote the code, your AI assistant did, or both.
3. **Within seconds**, the Guard runs every check automatically.
4. **Results appear on the PR:**
   - Green check = clean pass. Nothing found.
   - Orange "needs attention" = findings present; here they are in plain English with suggested fixes. (Uses GitHub's `action_required` state, which is highly visible — not the subtle grey "neutral" that looks like green.)
   - Red / blocked (opt-in only, Phase 9) = a CERTAIN-confidence, verified-dangerous fact. Merge is stopped until resolved.
5. **The Crew** (Phase 7+) posts plain-English explanations for each finding — what it is, why it matters, how to fix it.
6. **The dashboard** shows history, lets you tune settings, browse past analyses, and (later) chat with the AI explainer about any finding.

---

## 6. In Scope / Out of Scope

### In scope (full v1 — all phases)

- GitHub pull request analysis via GitHub App (webhook-based)
- All eight shipped checks (SQG001–SQG007 and SQG009); SQG008 is specified but not implemented
- GitHub Checks API output (findings visible directly on the PR)
- AI Crew plain-English explanations and fix suggestions (Phase 7)
- Dashboard: login, repo list, PR history, analysis detail
- Per-repo configuration via `.slopguard.yml` and dashboard editor
- Opt-in blocking (Phase 9, gated on measured false-positive rate below 1%)
- Human-in-the-loop bypass/approve flow for blocked PRs
- Multi-tenant (multiple users, multiple repos, org-level defaults)

### Out of scope for v1

- Support for GitLab, Azure DevOps, Bitbucket, Gitea (architecture has seams ready; adapters ship post-v1)
- Live secret verification (calling AWS/Stripe/GitHub with a leaked key to test if it works) — legal/ethical risk; deferred post-v1 with explicit user consent
- Risk scores (a single number like "Security Score: 74/100") — useful but risks being read as a guarantee; deferred
- Two-wave pipeline (fast checks now, deep checks update later) — over-engineered for MVP; deferred if users complain about speed
- AI Crew safety guardrails (detailed prompt engineering for the Crew's suggestions) — Phase 7+ concern
- Marketplace for third-party analyzer plugins — architecture supports it; product ships post-v1

---

## 7. Blocking Path (Opt-In, Phase 9)

Blocking — actually stopping a pull request from being merged — is a significant action. The path to enabling it:

1. **Gate on false-positive rate.** Blocking only becomes available after the product has measured a false-positive rate below 1% on real production PRs. This is a hard requirement, not a soft guideline.
2. **Opt-in per repository.** The repo owner enables it in `.slopguard.yml` or the dashboard (`block_mode: block`). Default is advisory-only.
3. **Block only on CERTAIN findings.** Only SQG001 (confirmed fake package) and SQG002 (verified secret) are block-eligible. CVEs (SQG004) are HIGH confidence, not CERTAIN for blocking purposes.
4. **Human bypass available.** Any blocked PR can be approved through the dashboard. The bypass is logged in the audit trail.
5. **Per-analyzer kill switch.** Any analyzer can be disabled instantly (environment variable or database flag) without redeployment, in case of a misfiring check.

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| False-positive rate on negative fixture set (clean code that should not flag) | 0% — hard gate, checked in CI on every code change |
| False-positive rate on real production PRs (required before blocking ships) | < 1% |
| Webhook acknowledgment time (how fast the PR gets a response) | < 500 ms (p95) |
| Full analysis completion time | < 30 seconds (p95) |
| Dashboard load time | < 1 second |
| Cost per PR analyzed | ~$0.003 |
| Cost per repo per month | ~$0.10 |
| Cost per user per month | ~$3.00 |

---

## 9. Release Scope Decision

**Founder decision: broad release.** No public launch until the complete product works end-to-end — all checks (SQG001–SQG007), dashboard, and AI Crew (Phase 7). The internal build order (v0.1 sequencing) is used for build discipline only — not as a public release gate.

First public release = full v1 through Phase 7 (Crew live), with blocking still opt-in per Phase 9.

Trade-off accepted: longer runway to first release, in exchange for a complete product on day one rather than a partial product that confuses early users.

---

## 10. Customer-Facing Naming Decision

- **Internal codename:** Slop Quarantine Guard (fine for internal docs, planning, repo names)
- **Working customer-facing title:** PR Quality & Security Gate
- **Final name:** To be decided before public launch. Must be neutral, professional, and not imply that users or their AI tools produce "slop."
- **Domain / brand:** TBD
