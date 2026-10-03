"""refresh_project: the checks around the data-layer working-copy refresh."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quodeq.core.run.job_status import JobStatus
from quodeq.core.types.working_copy_refresh import RefreshOutcome
from quodeq.data.fs.repo_refresh import RefreshResult
from quodeq.services.project_refresh import RefreshDeps, refresh_project

_REPORTS = "/reports"
_ORIGIN = "https://example.com/acme/app.git"


class _Provider:
    def __init__(self, infos: dict[str, dict], jobs: list | None = None) -> None:
        self._infos = infos
        self._jobs = jobs or []

    def get_project_info(self, reports_dir: str, project: str) -> dict | None:
        return self._infos.get(project)

    def list_evaluations(self, **_kwargs) -> list:
        return self._jobs


def _deps(calls: list, result: RefreshResult | None = None, pin=lambda url: ["pin"]) -> RefreshDeps:
    def refresh(path: Path, **kwargs) -> RefreshResult:
        calls.append((path, kwargs))
        return result or RefreshResult(RefreshOutcome.UPDATED, new_commits=3)

    return RefreshDeps(
        refresh=refresh, live_remote=lambda path: None, pin=pin,
        access_env=lambda url: {"TOKEN_FOR": url},
    )


def _info(path: Path, **extra) -> dict:
    return {"path": str(path), "originUrl": _ORIGIN, **extra}


def _running(project: str) -> SimpleNamespace:
    return SimpleNamespace(status=JobStatus.RUNNING, output_project=project)


def test_unknown_project_is_none(tmp_path: Path) -> None:
    assert refresh_project(_Provider({}), _REPORTS, "p", deps=_deps([])) is None


def test_project_without_remote_is_not_refreshable(tmp_path: Path) -> None:
    provider = _Provider({"p": {"path": str(tmp_path)}})
    calls: list = []

    result = refresh_project(provider, _REPORTS, "p", deps=_deps(calls))

    assert result.outcome == RefreshOutcome.NOT_REFRESHABLE
    assert calls == []


def test_missing_folder_is_not_refreshable(tmp_path: Path) -> None:
    provider = _Provider({"p": _info(tmp_path / "gone")})

    result = refresh_project(provider, _REPORTS, "p", deps=_deps([]))

    assert result.outcome == RefreshOutcome.NOT_REFRESHABLE


def test_user_folder_fast_forwards_under_pin_and_access_env(tmp_path: Path) -> None:
    calls: list = []

    result = refresh_project(_Provider({"p": _info(tmp_path)}), _REPORTS, "p", deps=_deps(calls))

    assert (result.outcome, result.new_commits) == (RefreshOutcome.UPDATED, 3)
    (path, kwargs), = calls
    assert path == tmp_path
    assert kwargs["hard_reset"] is False
    assert kwargs["git_config"] == ["pin"]
    assert kwargs["env"] == {"TOKEN_FOR": _ORIGIN}


def test_managed_clone_is_hard_reset(tmp_path: Path) -> None:
    calls: list = []
    provider = _Provider({"p": _info(tmp_path, ephemeral=True)})

    refresh_project(provider, _REPORTS, "p", deps=_deps(calls))

    assert calls[0][1]["hard_reset"] is True


def test_running_evaluation_of_the_project_blocks(tmp_path: Path) -> None:
    calls: list = []
    provider = _Provider({"p": _info(tmp_path)}, jobs=[_running("p")])

    result = refresh_project(provider, _REPORTS, "p", deps=_deps(calls))

    assert result.outcome == RefreshOutcome.BUSY
    assert calls == []


def test_running_evaluation_of_a_scoped_sibling_blocks(tmp_path: Path) -> None:
    provider = _Provider(
        {"p": _info(tmp_path), "child": _info(tmp_path, scopePath="src")}, jobs=[_running("child")],
    )

    result = refresh_project(provider, _REPORTS, "p", deps=_deps([]))

    assert result.outcome == RefreshOutcome.BUSY


def test_finished_evaluation_does_not_block(tmp_path: Path) -> None:
    done = SimpleNamespace(status=JobStatus.DONE, output_project="p")
    provider = _Provider({"p": _info(tmp_path)}, jobs=[done])

    result = refresh_project(provider, _REPORTS, "p", deps=_deps([]))

    assert result.outcome == RefreshOutcome.UPDATED


def test_internal_remote_host_is_refused_before_git(tmp_path: Path) -> None:
    calls: list = []

    def pin(url: str) -> list[str]:
        raise ValueError("example.com resolves to a private/internal address")

    result = refresh_project(_Provider({"p": _info(tmp_path)}), _REPORTS, "p", deps=_deps(calls, pin=pin))

    assert result.outcome == RefreshOutcome.FETCH_FAILED
    assert "internal" in result.detail
    assert calls == []


def test_a_second_refresh_runs_after_the_first_ends(tmp_path: Path) -> None:
    provider = _Provider({"p": _info(tmp_path)})

    first = refresh_project(provider, _REPORTS, "p", deps=_deps([]))
    second = refresh_project(provider, _REPORTS, "p", deps=_deps([]))

    assert (first.outcome, second.outcome) == (RefreshOutcome.UPDATED, RefreshOutcome.UPDATED)


def test_refresh_of_a_folder_already_refreshing_is_busy(tmp_path: Path) -> None:
    provider = _Provider({"p": _info(tmp_path)})
    nested: list = []

    def refresh(path: Path, **_kwargs) -> RefreshResult:
        nested.append(refresh_project(provider, _REPORTS, "p", deps=_deps([])))
        return RefreshResult(RefreshOutcome.UP_TO_DATE)

    deps = RefreshDeps(refresh=refresh, live_remote=lambda p: None, pin=lambda u: [], access_env=lambda u: None)
    outer = refresh_project(provider, _REPORTS, "p", deps=deps)

    assert outer.outcome == RefreshOutcome.UP_TO_DATE
    assert nested[0].outcome == RefreshOutcome.BUSY
