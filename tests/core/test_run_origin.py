"""Where a run came from, read from the GitHub Actions environment the CLI runs in."""
from __future__ import annotations

from quodeq.core.run.origin import RunOrigin, origin_from_env

_GH = {
    "GITHUB_ACTIONS": "true", "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "quodeq/quodeq", "GITHUB_RUN_ID": "987", "GITHUB_REF_NAME": "1402/merge",
}


def test_a_pull_request_event_is_a_pr_review() -> None:
    origin = origin_from_env({**_GH, "GITHUB_EVENT_NAME": "pull_request", "GITHUB_WORKFLOW": "Quodeq Review"},
                             {"pull_request": {"number": 1402}})
    assert origin.kind == "ci"
    assert origin.pr == 1402
    assert origin.pr_url == "https://github.com/quodeq/quodeq/pull/1402"
    assert origin.run_url == "https://github.com/quodeq/quodeq/actions/runs/987"


def test_a_dispatched_review_takes_the_pr_from_its_input() -> None:
    origin = origin_from_env({**_GH, "GITHUB_EVENT_NAME": "workflow_dispatch"}, {"inputs": {"pr_number": "77"}})
    assert origin.pr == 77
    assert origin.pr_url == "https://github.com/quodeq/quodeq/pull/77"


def test_the_schedule_is_the_nightly() -> None:
    origin = origin_from_env({**_GH, "GITHUB_EVENT_NAME": "schedule", "GITHUB_WORKFLOW": "Quodeq Nightly"}, {})
    assert (origin.kind, origin.event, origin.workflow, origin.pr) == ("ci", "schedule", "Quodeq Nightly", None)


def test_outside_github_actions_it_is_the_cli() -> None:
    assert origin_from_env({}, None) == RunOrigin(kind="cli")


def test_a_malformed_event_never_breaks_a_run() -> None:
    origin = origin_from_env({**_GH, "GITHUB_EVENT_NAME": "pull_request"}, {"pull_request": {"number": "x"}, "inputs": "?"})
    assert origin.kind == "ci"
    assert origin.pr is None


def test_round_trips_through_status_json() -> None:
    origin = origin_from_env({**_GH, "GITHUB_EVENT_NAME": "pull_request"}, {"pull_request": {"number": 5}})
    assert RunOrigin.from_dict(origin.to_dict()) == origin
    assert RunOrigin.from_dict("nonsense") is None
