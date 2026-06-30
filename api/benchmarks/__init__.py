"""AI-tool Trust Score benchmark harness (Sprint C, growth wedge).

Scores any AI coding tool's generated code through the same SQG001–007 engine the
product runs, producing a reproducible, neutral Trust Score. The harness scores
*code samples*; how the samples are produced (paste, file, or a live tool API) is
a separate, swappable concern — so the whole thing runs deterministically offline,
and live API integration is a thin adapter added once keys exist.

See METHODOLOGY.md for the published scoring method (neutral + reproducible — the
honesty rule applies to the leaderboard exactly as it does to a scan finding).
"""
