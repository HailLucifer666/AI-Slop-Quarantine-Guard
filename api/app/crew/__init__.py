"""The Crew — the advisory layer that explains findings but never decides them.

No longer a stub: ``explainer.py`` implements ``explain_finding``, and it is reachable at
``POST /api/crew/explain`` via ``app/crew_router.py``, mounted in ``main.py``. It takes one
Guard finding and returns plain English for a non-technical reader — what it is, why it
matters, how to fix it.

What has NOT been built is the Crew's role in a scan: nothing calls the explainer during
analysis, so a stored scan carries no explanations and the report renders none. It is an
endpoint the dashboard can ask, not a stage of the pipeline.

The one-directional rule holds regardless (PRD §3): findings flow into the Crew for
explanation, and nothing flows back. The Crew cannot change a conclusion, a severity or a
block decision, and any failure returns None so the finding stands on its own.
"""
