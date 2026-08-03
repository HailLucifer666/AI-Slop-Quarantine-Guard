"""Strix (github.com/usestrix/strix) advisory integration — Phase 5.

Strix is an autonomous, LLM-driven pentest agent: it runs the target dynamically
and reports vulnerability *hypotheses*, not reproducible facts. Per this
product's honesty contract, its output is a strictly separate, advisory-only
lane — never CERTAIN, never block-eligible, never merged into the Guard's
findings or passed to app.checks. See app.strix.parser for the enforced
mapping and its module docstring for what's real vs. deferred.
"""
