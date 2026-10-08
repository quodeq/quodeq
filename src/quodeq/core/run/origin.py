"""Where a run came from: a CI workflow (the nightly, a PR review) or the CLI.

``origin_from_env`` is pure: the caller hands it the environment and the
parsed GitHub event payload, so it never touches files or ``os.environ``.
The CLI records the result in status.json at run start; the dashboard reads
it back to label a run it did not start ("nightly", "PR review #1402") and
to link it to its pull request.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

ORIGIN_CI = "ci"
ORIGIN_CLI = "cli"

_ENV_ACTIONS = "GITHUB_ACTIONS"
_ACTIONS_ON = "true"


@dataclass(frozen=True, slots=True)
class RunOrigin:
    """Where a run came from. ``kind`` is ``"ci"`` or ``"cli"``; the rest is CI-only."""

    kind: str
    event: str | None = None
    workflow: str | None = None
    ref: str | None = None
    pr: int | None = None
    pr_url: str | None = None
    run_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """The status.json form: unset fields left out."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: object) -> RunOrigin | None:
        """Rebuild from status.json; None for anything that is not an origin."""
        if not isinstance(data, Mapping) or data.get("kind") not in (ORIGIN_CI, ORIGIN_CLI):
            return None
        pr = data.get("pr")
        return cls(
            kind=data["kind"],
            event=_text(data.get("event")),
            workflow=_text(data.get("workflow")),
            ref=_text(data.get("ref")),
            pr=pr if isinstance(pr, int) and not isinstance(pr, bool) else None,
            pr_url=_text(data.get("pr_url")),
            run_url=_text(data.get("run_url")),
        )


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _pr_number(event: object) -> int | None:
    """The PR a pull_request event is about, or a dispatched review's pr_number input."""
    if not isinstance(event, Mapping):
        return None
    pull = event.get("pull_request")
    if isinstance(pull, Mapping):
        number = _as_int(pull.get("number"))
        if number is not None:
            return number
    inputs = event.get("inputs")
    return _as_int(inputs.get("pr_number")) if isinstance(inputs, Mapping) else None


def origin_from_env(env: Mapping[str, str], event: object) -> RunOrigin:
    """The origin of a run started in *env*, with *event* the parsed GITHUB_EVENT_PATH payload."""
    if env.get(_ENV_ACTIONS) != _ACTIONS_ON:
        return RunOrigin(kind=ORIGIN_CLI)
    server, repo = env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY")
    base = f"{server}/{repo}" if server and repo else None
    pr = _pr_number(event)
    run_id = env.get("GITHUB_RUN_ID")
    return RunOrigin(
        kind=ORIGIN_CI,
        event=_text(env.get("GITHUB_EVENT_NAME")),
        workflow=_text(env.get("GITHUB_WORKFLOW")),
        ref=_text(env.get("GITHUB_REF_NAME")),
        pr=pr,
        pr_url=f"{base}/pull/{pr}" if base and pr is not None else None,
        run_url=f"{base}/actions/runs/{run_id}" if base and run_id else None,
    )
