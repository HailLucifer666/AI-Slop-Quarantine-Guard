"""analyze_pr: an internal-error failure after the Check Run opens must resolve
it to a visible terminal state (never left stuck "in_progress" forever — that
would make a required status check permanently unmergeable) and must record the
failure to the audit trail, mirroring how a whole-repo scan's failure is never
silently dropped (store.fail_scan)."""

import pytest

from app import worker


@pytest.mark.asyncio
async def test_stuck_check_run_resolved_and_failure_recorded(monkeypatch):
    events = []

    async def fake_token(_installation_id):
        return "tok"

    async def fake_create_check_run(_repo, _sha, _token):
        return 42  # the check run opens successfully

    async def fake_fetch_pr_diff(_repo, _pr, _token):
        raise RuntimeError("GitHub API blew up mid-fetch")

    update_calls = []

    async def fake_update_check_run(repo, check_run_id, conclusion, summary, token, **kw):
        update_calls.append((repo, check_run_id, conclusion, summary))
        return True

    async def fake_record_event(action, details):
        events.append((action, details))

    monkeypatch.setattr(worker, "get_installation_token", fake_token)
    monkeypatch.setattr(worker, "create_check_run", fake_create_check_run)
    monkeypatch.setattr(worker, "fetch_pr_diff", fake_fetch_pr_diff)
    monkeypatch.setattr(worker, "update_check_run", fake_update_check_run)
    monkeypatch.setattr(worker, "record_event", fake_record_event)

    with pytest.raises(RuntimeError, match="blew up"):
        await worker.analyze_pr("octo/repo", 7, "abc123", 999)

    # The Check Run was resolved to a visible, honest terminal state — never left
    # stuck "in_progress", and never "neutral" (which renders as a green check).
    assert len(update_calls) == 1
    repo, check_run_id, conclusion, summary = update_calls[0]
    assert repo == "octo/repo"
    assert check_run_id == 42
    assert conclusion == "action_required"
    assert "internal error" in summary.lower()

    # The failure is durably recorded, not just logged to stdout.
    assert len(events) == 1
    action, details = events[0]
    assert action == "pr_analysis.failed"
    assert details["repo"] == "octo/repo"
    assert details["pr_number"] == 7
    assert details["check_run_id"] == 42
    assert "blew up" in details["error"]


@pytest.mark.asyncio
async def test_failure_before_check_run_opens_does_not_call_update(monkeypatch):
    # If create_check_run itself never returned an id (e.g. the API call failed),
    # there is no check run to resolve — only the record_event call should fire.
    events = []

    async def fake_token(_installation_id):
        return "tok"

    async def fake_create_check_run(_repo, _sha, _token):
        return None

    async def fake_fetch_pr_diff(_repo, _pr, _token):
        raise RuntimeError("boom")

    update_calls = []

    async def fake_update_check_run(*a, **kw):
        update_calls.append((a, kw))
        return True

    async def fake_record_event(action, details):
        events.append((action, details))

    monkeypatch.setattr(worker, "get_installation_token", fake_token)
    monkeypatch.setattr(worker, "create_check_run", fake_create_check_run)
    monkeypatch.setattr(worker, "fetch_pr_diff", fake_fetch_pr_diff)
    monkeypatch.setattr(worker, "update_check_run", fake_update_check_run)
    monkeypatch.setattr(worker, "record_event", fake_record_event)

    with pytest.raises(RuntimeError, match="boom"):
        await worker.analyze_pr("octo/repo", 7, "abc123", 999)

    assert update_calls == []  # nothing to resolve
    assert len(events) == 1 and events[0][0] == "pr_analysis.failed"


@pytest.mark.asyncio
async def test_successful_analysis_does_not_record_a_failure_event(monkeypatch):
    events = []

    async def fake_token(_installation_id):
        return "tok"

    async def fake_create_check_run(_repo, _sha, _token):
        return 42

    async def fake_fetch_pr_diff(_repo, _pr, _token):
        return None  # "nothing to analyze" path — a clean, successful outcome

    update_calls = []

    async def fake_update_check_run(repo, check_run_id, conclusion, summary, token, **kw):
        update_calls.append((repo, check_run_id, conclusion, summary))
        return True

    async def fake_record_event(action, details):
        events.append((action, details))

    monkeypatch.setattr(worker, "get_installation_token", fake_token)
    monkeypatch.setattr(worker, "create_check_run", fake_create_check_run)
    monkeypatch.setattr(worker, "fetch_pr_diff", fake_fetch_pr_diff)
    monkeypatch.setattr(worker, "update_check_run", fake_update_check_run)
    monkeypatch.setattr(worker, "record_event", fake_record_event)

    result = await worker.analyze_pr("octo/repo", 7, "abc123", 999)

    assert result["files"] == {}
    assert update_calls == [("octo/repo", 42, "success", "✅ Nothing to analyze in this change.")]
    assert events == []
