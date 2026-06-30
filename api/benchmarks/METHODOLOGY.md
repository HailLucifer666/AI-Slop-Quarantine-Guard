# AI Coding Tool Trust Score — Methodology (v1.0)

A public, reproducible benchmark of how much *slop* different AI coding tools emit.
Neutrality and reproducibility are non-negotiable: this is the same honesty bar the
product holds itself to on every scan. If we can't measure a tool fairly and
repeatably, we don't publish a number for it.

## What the score measures

For each tool we collect its code answers to a **fixed corpus of prompts**
(`corpus.py`), run every answer through the **exact engine the product ships**
(`app.scan.run_scan` → analyzers SQG001–SQG007), and convert the findings into a
0–100 Trust Score. Higher = less slop.

We measure only what the engine can **prove or strongly evidence** — hallucinated
dependencies, leaked secrets, known-vulnerable pins, risky licenses, dangerous code
patterns, placeholder stubs, and typosquat look-alikes. We do **not** score style,
cleverness, or whether the code "works" — only verifiable safety/quality signals.

## The formula

Per code sample:

```
penalty     = Σ weight(finding.confidence)
trust_score = max(0, 100 − penalty)
```

| Confidence | Weight | Meaning |
|-----------|--------|---------|
| CERTAIN   | 25 | A reproducible fact (e.g. a package that 404s on its registry, a live-format secret). |
| HIGH      | 8  | Strong evidence, not a proven fact (advisory). |
| MEDIUM    | 3  | Worth a look (advisory). |

Per tool: the **mean** of its per-sample scores across the corpus.

The weights are the one editorial choice in the method. They are published here,
versioned, and applied identically to every tool. Changing them — or the corpus —
**bumps `METHODOLOGY_VERSION`**, so scores computed under different rules are never
silently compared.

## Why this is neutral

- **Same engine, same corpus, same weights** for every tool. No per-tool tuning.
- **Deterministic.** Same samples in → same score out. No randomness, no timestamps
  in the scored math.
- **Auditable.** Every score ships with its raw findings (rule id, file, line,
  confidence), so anyone can recompute it by hand.
- **The corpus is fixed and public.** A tool can't be advantaged by a friendlier set
  of tasks.

## Provenance (the honesty gate)

Every leaderboard carries a `data_source` label. A leaderboard is **only** presented
as real when that label marks real tool runs (e.g. `live:2026-06-30`). Demo data is
labelled `sample-fixtures` and must be shown as such — we never present fabricated or
placeholder rankings as measured results.

## Running it

```
python -m benchmarks.run <samples_root> leaderboard.json --source=live:YYYY-MM-DD
```

`<samples_root>/<tool>/<task_id>/<files…>` — one leaf directory per tool answer.

## Known limits (stated, not hidden)

- v1.0 scores the engine's current coverage; gaps in the engine are gaps in the score.
- Network-backed checks (existence, CVE, license) depend on registry/OSV reachability;
  per the product's fail-safe rule an outage downgrades to advisory rather than
  inventing a CERTAIN penalty, so a score computed during an outage may be *higher*
  than one computed with full connectivity. Re-run with connectivity before publishing.
- Live tool adapters (calling each AI tool's API to generate the samples) are added
  once API keys are provided; until then the harness scores samples collected manually.
