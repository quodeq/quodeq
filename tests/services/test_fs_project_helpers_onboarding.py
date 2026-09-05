"""Tests for the onboardingCompletedAt heal in _build_project_entry.

A wizard-created project gets ``onboardingCompletedAt: null`` at registration
time. Setup completion is stamped when an evaluation starts (see
evaluation_mixin), but records created before that stamp existed are stuck at
null forever despite having runs. The list read heals those: null + runs =>
timestamp. Run-less records stay null (they are genuinely mid-setup), and the
shared-repo route (backfill=False) never writes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from quodeq.services import _fs_project_helpers as helpers
from quodeq.services._fs_project_helpers import _build_project_entry, find_existing_project
from quodeq.services._fs_projects import update_project_path
from quodeq.services._repo_index import _load_repo_index, _repo_index_key, _save_repo_index
from quodeq.services.project_registration import register_project
from quodeq.data.fs.report_parser.runs import RunInfo


def _make_project(tmp_path: Path, name: str = "proj-1", *, onboarding=None) -> Path:
    project_dir = tmp_path / name
    project_dir.mkdir()
    (project_dir / "repository_info.json").write_text(json.dumps({
        "name": name,
        "location": "local",
        "path": str(tmp_path / "src" / name),
        "onboardingCompletedAt": onboarding,
    }))
    return project_dir


def _run(run_id: str, date_iso: str | None) -> RunInfo:
    return RunInfo(run_id=run_id, date_iso=date_iso, date_label=run_id)


def _read_field(project_dir: Path):
    return json.loads((project_dir / "repository_info.json").read_text())["onboardingCompletedAt"]


def test_entry_heals_null_onboarding_to_first_run_date(tmp_path):
    project_dir = _make_project(tmp_path, onboarding=None)
    # list_runs order: newest first, so the last element is the first run.
    runs = [
        _run("2026-01-05_00-00-00", "2026-01-05T00:00:00"),
        _run("2025-12-02_00-00-00", "2025-12-02T00:00:00"),
    ]

    entry = _build_project_entry(tmp_path, "proj-1", runs)

    assert entry.onboarding_completed_at == "2025-12-02T00:00:00"
    assert _read_field(project_dir) == "2025-12-02T00:00:00"


def test_entry_heals_null_onboarding_without_run_date(tmp_path):
    """A run with no parseable date still proves an evaluation happened."""
    project_dir = _make_project(tmp_path, onboarding=None)

    entry = _build_project_entry(tmp_path, "proj-1", [_run("some-run", None)])

    assert isinstance(entry.onboarding_completed_at, str) and entry.onboarding_completed_at
    assert _read_field(project_dir) == entry.onboarding_completed_at


def test_entry_keeps_null_onboarding_without_runs(tmp_path):
    project_dir = _make_project(tmp_path, onboarding=None)

    entry = _build_project_entry(tmp_path, "proj-1", [])

    assert entry.onboarding_completed_at is None
    assert _read_field(project_dir) is None


def test_entry_preserves_existing_onboarding_stamp(tmp_path):
    project_dir = _make_project(tmp_path, onboarding="2025-11-01T00:00:00Z")

    entry = _build_project_entry(
        tmp_path, "proj-1", [_run("2025-12-02_00-00-00", "2025-12-02T00:00:00")],
    )

    assert entry.onboarding_completed_at == "2025-11-01T00:00:00Z"
    assert _read_field(project_dir) == "2025-11-01T00:00:00Z"


def test_entry_backfill_false_never_writes(tmp_path):
    """The shared-repo route lists clones read-only: no heal, no dirty worktree."""
    project_dir = _make_project(tmp_path, onboarding=None)
    info_path = project_dir / "repository_info.json"
    before = info_path.read_text()

    entry = _build_project_entry(
        tmp_path, "proj-1",
        [_run("2025-12-02_00-00-00", "2025-12-02T00:00:00")],
        backfill=False,
    )

    assert entry.onboarding_completed_at is None
    assert info_path.read_text() == before


def _make_repo(base: Path, name: str) -> Path:
    repo_dir = base / "repos" / name
    repo_dir.mkdir(parents=True)
    (repo_dir / "file.py").write_text("x = 1\n")
    return repo_dir


def test_find_existing_project_uses_index_then_self_heals_via_walk_fallback(tmp_path, monkeypatch):
    """The happy path must hit .repo_index.json, not read every project's
    repository_info.json. Deleting the index must not cause a false
    negative: the directory-walk fallback still finds every project and
    repairs the index for the next lookup."""
    reports = tmp_path / "reports"
    reports.mkdir()
    repos = [_make_repo(tmp_path, name) for name in ("alpha", "beta", "gamma")]
    uuids = [register_project(str(repo), None, str(reports)) for repo in repos]

    index_path = reports / ".repo_index.json"
    assert index_path.exists()
    assert set(_load_repo_index(reports).values()) == set(uuids)

    # An index hit reads exactly one record — the candidate it is about to
    # return, to confirm the entry isn't stale. It must never read the other
    # projects: that O(n) sweep is what the index exists to avoid.
    reads: list[str] = []
    real_read = helpers.read_repository_info

    def _counting_read(project_dir):
        reads.append(Path(project_dir).name)
        return real_read(project_dir)

    monkeypatch.setattr(helpers, "read_repository_info", _counting_read)
    for repo, uuid in zip(repos, uuids):
        reads.clear()
        assert find_existing_project(str(reports), str(repo), None) == uuid
        assert reads == [uuid], reads
    monkeypatch.undo()

    # Blow away the index entirely: every lookup must still resolve via the
    # directory-walk fallback, and self-heal the index as it goes.
    index_path.unlink()
    for repo, uuid in zip(repos, uuids):
        assert find_existing_project(str(reports), str(repo), None) == uuid

    assert index_path.exists()
    assert set(_load_repo_index(reports).values()) == set(uuids)


def test_find_existing_project_ignores_index_entry_left_by_a_path_move(tmp_path):
    """A project that moved must stop claiming the path it left behind.

    ``path`` is one third of the index key, so a ``PUT /api/projects/<id>/path``
    used to leave the old (name, path, scopePath) key mapped at the project's
    uuid. Registering a different repo at the freed path then hit that entry
    and got refused as a "duplicate" of a project that isn't there any more.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    repo = _make_repo(tmp_path, "alpha")
    uuid = register_project(str(repo), None, str(reports))

    moved_to = tmp_path / "moved" / "alpha"
    moved_to.mkdir(parents=True)
    assert update_project_path(str(reports), uuid, str(moved_to)) is True

    assert find_existing_project(str(reports), str(repo), None) is None
    assert find_existing_project(str(reports), str(moved_to), None) == uuid


def test_find_existing_project_drops_an_index_hit_its_record_contradicts(tmp_path):
    """Any stale index entry — an out-of-band path rewrite, a corrupt file, a
    concurrent create/delete — must degrade to the walk, not to a wrong uuid.
    The bad entry is purged so it can't mislead the next lookup either."""
    reports = tmp_path / "reports"
    reports.mkdir()
    repo = _make_repo(tmp_path, "alpha")
    uuid = register_project(str(repo), None, str(reports))

    unclaimed = tmp_path / "repos" / "unclaimed"
    unclaimed.mkdir(parents=True)
    stale_key = _repo_index_key("unclaimed", str(unclaimed.resolve()), None)
    index = _load_repo_index(reports)
    index[stale_key] = uuid
    _save_repo_index(reports, index)

    assert find_existing_project(str(reports), str(unclaimed), None) is None
    assert stale_key not in _load_repo_index(reports)
    # The project's genuine identity is untouched by the purge.
    assert find_existing_project(str(reports), str(repo), None) == uuid


def test_find_existing_project_resolves_a_url_registered_project(tmp_path):
    """A URL-registered project must still be found by its URL.

    The index key holds the URL, but registration rewrites the record's
    ``path`` to the local clone directory, so verifying an index hit against
    that record can never succeed for a URL identity. Doing it anyway purged
    the valid entry on every lookup, so re-registering an already-cloned
    remote reported "created" instead of "duplicate" and re-cloned it.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    clone_dest = tmp_path / "code"
    clone_dest.mkdir()
    url = "https://github.com/example/repo.git"

    def fake_clone(_url, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "README.md").write_text("# fake\n")
        (Path(dest) / ".git").mkdir()

    with patch("quodeq.services.project_registration.run_git_clone", side_effect=fake_clone):
        uuid = register_project(url, None, str(reports), clone_dest=str(clone_dest))

    key = _repo_index_key("repo", url, None)
    assert _load_repo_index(reports).get(key) == uuid

    # Both the lookup and the index entry survive repeated duplicate checks.
    assert find_existing_project(str(reports), url, None) == uuid
    assert find_existing_project(str(reports), url, None) == uuid
    assert _load_repo_index(reports).get(key) == uuid


def test_find_existing_project_resolves_a_scoped_registration(tmp_path):
    """A scoped project must still be found by (name, path, scopePath).

    The index key carries the BARE project name, but the scoped child's
    record is written under the compound ``"<name>/<scope>"`` name, so
    verifying an index hit against that record can never succeed for a
    scoped identity. Doing it anyway purged the valid entry on every lookup
    and returned None, so re-registering an existing scope reported
    "created" instead of "duplicate".
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    repo = _make_repo(tmp_path, "alpha")
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("y = 2\n")

    uuid = register_project(str(repo), None, str(reports), "src")

    key = _repo_index_key("alpha", str(repo.resolve()), "src")
    assert _load_repo_index(reports).get(key) == uuid

    # Both the lookup and the index entry survive repeated duplicate checks.
    assert find_existing_project(str(reports), str(repo), "src") == uuid
    assert find_existing_project(str(reports), str(repo), "src") == uuid
    assert _load_repo_index(reports).get(key) == uuid


def test_scoped_project_stays_findable_after_a_path_move(tmp_path):
    """A scoped project must survive ``PUT /api/projects/<id>/path``.

    The index key carries the BARE project name, but the scoped child's
    record is written under the compound ``"<name>/<scope>"`` name. Rekeying
    on the record's own ``name`` installed ``"alpha/src"`` as the key, which
    find_existing_project (which computes ``"alpha"``) can never look up, so
    the moved project went unfindable by its own identity.
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    repo = _make_repo(tmp_path, "alpha")
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("y = 2\n")

    uuid = register_project(str(repo), None, str(reports), "src")

    moved_to = tmp_path / "moved" / "alpha"
    moved_to.mkdir(parents=True)
    assert update_project_path(str(reports), uuid, str(moved_to)) is True

    moved_key = _repo_index_key("alpha", str(moved_to.resolve()), "src")
    assert _load_repo_index(reports).get(moved_key) == uuid
    assert find_existing_project(str(reports), str(moved_to), "src") == uuid


def test_find_existing_project_survives_a_corrupt_index_file(tmp_path):
    """Unparseable index bytes are treated as an empty index: the walk still
    finds the project and rewrites a usable index."""
    reports = tmp_path / "reports"
    reports.mkdir()
    repo = _make_repo(tmp_path, "alpha")
    uuid = register_project(str(repo), None, str(reports))

    (reports / ".repo_index.json").write_text("{ this is not json", encoding="utf-8")

    assert find_existing_project(str(reports), str(repo), None) == uuid
    assert _load_repo_index(reports) == {
        _repo_index_key("alpha", str(repo.resolve()), None): uuid,
    }


def test_find_existing_project_logs_malformed_repo_identifier(caplog, tmp_path):
    """A repo identifier is_repo_url can't classify must not fail silently:
    the duplicate check falls back to 'no match', but an operator needs a
    trace to see which malformed identifier was rejected."""
    with patch(
        "quodeq.shared.utils.is_repo_url",
        side_effect=ValueError("cannot classify repo identifier"),
    ), caplog.at_level(logging.WARNING):
        result = find_existing_project(str(tmp_path), "not a valid repo!!", None)
    assert result is None
    assert any("not a valid repo!!" in r.message for r in caplog.records)
