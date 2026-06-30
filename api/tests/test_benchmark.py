"""Sprint C Trust Score harness: scoring is reproducible, neutral, and honest about
provenance. Kept network-free — samples use no manifests, so only offline analyzers
(secrets, placeholders) fire and the assertions stay deterministic."""

import pytest

from benchmarks.harness import run_benchmark, score_sample
from benchmarks.run import load_samples
from benchmarks.scoring import MAX_SCORE, score_findings


# --- pure scoring -----------------------------------------------------------

def test_clean_sample_scores_full_marks():
    assert score_findings([])["trust_score"] == MAX_SCORE


def test_penalties_by_confidence_tier():
    findings = [
        {"confidence": "CERTAIN"},  # -25
        {"confidence": "MEDIUM"},   # -3
    ]
    s = score_findings(findings)
    assert s["trust_score"] == 72
    assert s["penalty"] == 28
    assert s["by_confidence"] == {"CERTAIN": 1, "HIGH": 0, "MEDIUM": 1}
    assert s["findings_total"] == 2


def test_score_floors_at_zero():
    findings = [{"confidence": "CERTAIN"}] * 10  # -250, clamped
    assert score_findings(findings)["trust_score"] == 0


# --- end-to-end through the real engine -------------------------------------

@pytest.mark.asyncio
async def test_score_sample_uses_the_real_engine():
    clean = await score_sample({"README.md": "# hi\n"})
    assert clean["trust_score"] == MAX_SCORE

    slop = await score_sample({"config.py": 'KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: implement\n'})
    assert slop["trust_score"] < clean["trust_score"]  # secret + placeholder cost points
    assert slop["by_confidence"]["CERTAIN"] >= 1       # the secret is a proven fact


@pytest.mark.asyncio
async def test_run_benchmark_ranks_cleaner_tool_first():
    samples = {
        "ToolSlop": {"t1": {"a.py": 'KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: x\n'}},
        "ToolClean": {"t1": {"a.py": "x = 1\n"}},
    }
    board = await run_benchmark(samples, data_source="sample-fixtures")
    assert [t["tool"] for t in board["tools"]] == ["ToolClean", "ToolSlop"]
    assert board["tools"][0]["trust_score"] > board["tools"][1]["trust_score"]
    assert board["data_source"] == "sample-fixtures"  # provenance preserved (honesty gate)
    assert board["methodology_version"] == "1.0"


@pytest.mark.asyncio
async def test_scoring_is_deterministic():
    files = {"a.py": 'KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: x\n'}
    first = await score_sample(files)
    second = await score_sample(files)
    assert first["trust_score"] == second["trust_score"]


# --- sample loading ---------------------------------------------------------

def test_load_samples_reads_tool_task_tree(tmp_path):
    leaf = tmp_path / "ToolA" / "py-http-client"
    leaf.mkdir(parents=True)
    (leaf / "main.py").write_text("x = 1\n", encoding="utf-8")
    (leaf / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")

    samples = load_samples(str(tmp_path))
    assert set(samples) == {"ToolA"}
    assert set(samples["ToolA"]["py-http-client"]) == {"main.py", "requirements.txt"}
