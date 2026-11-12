"""The Guard's deterministic checks — SQG001-SQG007 and SQG009.

This file used to claim "each analyzer implements the Analyzer protocol and registers
itself". Neither half was ever true — and the unused ``Analyzer`` protocol was removed
(2026-11-12): every check is a module-level async function
``check_x(diff, repo_context) -> List[Finding]``, and they are collected by the explicit
ordered list in ``scan.py::run_scan`` (mirrored for the PR path in ``worker.py``), not by
self-registration. Adding a check means writing that function and adding it to those two
lists, plus a capability entry in ``coverage.py`` so it reports what it examined.

Every check here answers with facts and degrades to advisory when it cannot: that is the
line between this package and ``app.crew``, which explains findings but never decides them.
"""
