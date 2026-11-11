# AI Slop Quarantine Guard — README

## What This Is

A **GitHub App + dashboard** that automatically checks every pull request against the same quality and security standards that the biggest tech companies use—before code goes live.

You install it on your GitHub repo (one click). When a PR opens, it runs:
- Fake/hallucinated package detector
- Leaked secret scanner
- Vulnerable dependency finder
- Incomplete/placeholder code detector
- License compatibility checker
- Code security patterns (SAST)
- AI reasoning scratchpads

Within seconds, results land on the PR. **Green** = clean. **Orange** (needs attention) = problems found, explained in plain English with fixes. **Red** (only if you enable it) = a proven-dangerous fact; merge is blocked until fixed.

A private dashboard shows your PR history, lets you tune settings, and explains findings in AI-powered plain English.

## The Promise (Not "Hackproof")

We do NOT claim to catch everything or make your code perfectly safe—nobody can. The honest promise is:

**"We run every known check the best companies run, and we catch everything those checks can catch. We never lie to you about a fact."**

Every finding is either a **provable fact** (a leaked password, a package that doesn't exist, a known vulnerability) or an **advisory** (this code pattern might be risky; here's why). We're transparent about which is which.

## Quick Start

1. **Install the app** on your GitHub repo: [Coming Soon]
2. **Open a pull request** (write code, make a change, push).
3. **Within seconds**, check the PR for the Guard's findings.
4. **Fix any issues** the Guard caught (or approve them in the dashboard).
5. **Merge.**

For detailed setup and configuration, see `BUILD_GUIDE.md`.

## The Two Layers (Keep Them Straight)

### The Guard (Deterministic)
Runs proven, fact-based tools in isolation. Blocks ONLY on things that are provably wrong (leaked secret with valid checksum, package that doesn't exist in any registry, exact CVE match). Never guesses.

### The Crew (AI Advisor, Phase 7+)
Once the Guard reports its findings, Claude Haiku reads them and explains each one in plain English for non-coders: "What happened, why it matters, how to fix it." Suggests fixes. Never blocks on its own. Advisory only.

## What's In The Box

- **GitHub App** (Python 3.12 + FastAPI)
- **Background worker** (Redis + arq, runs checks in parallel)
- **Database** (PostgreSQL via Supabase, tracks history)
- **Dashboard** (Next.js, Vercel, shows PR results over time)
- **7 specialized checkers** (each proven to catch what it targets)

## Tech You'll See

- **Backend:** Python 3.12, FastAPI, arq, SQLAlchemy 2.0
- **Database:** PostgreSQL (Supabase)
- **Queue:** Redis (Upstash)
- **Frontend:** Next.js 15, TypeScript, Tailwind, shadcn/ui
- **AI:** Claude Haiku 4.5 (Gemini 2.5 Flash-Lite fallback)
- **Hosting:** Fly.io (API + worker), Vercel (dashboard), Cloudflare (security)

## Where to Go From Here

- **Want to understand the terms?** → `GLOSSARY.md`
- **Want to see every technology and why?** → `TECH_STACK.md`
- **Want to understand what each check does?** → `CHECKS_CATALOG.md`
- **Want the full database schema?** → `DATA_MODEL.md`
- **Want to see all API endpoints?** → `API_SPEC.md`
- **Want to know how we keep secrets safe?** → `SECURITY.md`
- **Want the step-by-step setup guide?** → `BUILD_GUIDE.md`
- **Already set up, and something is fighting you?** → `LOCAL_DEV.md`
- **Want to deploy to production?** → `DEPLOYMENT.md`
- **Want to see the build plan?** → `ROADMAP.md`
- **Want to understand the big decisions?** → `DECISIONS.md`
- **Want to contribute?** → `../CONTRIBUTING.md`

## Why This Matters

If you use AI to code—Claude, ChatGPT, Copilot, whatever—you ship code you can't fully verify. The Guard gives you a safety net. It doesn't promise perfection; it promises *honesty and the best tools available*.

---

**Status:** Greenfield. Scaffolding + Phase 1 underway. First public release after Phase 7 (full Guard + Crew).
