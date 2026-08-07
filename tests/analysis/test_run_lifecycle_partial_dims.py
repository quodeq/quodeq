"""A run that ends with dimensions still unscored must say so.

The failure-streak circuit breaker aborts the remaining dimensions from
inside the pipeline, so no exception reaches the lifecycle context and the
run exits through the clean DONE path. Every dimension that never got a
turn stayed at ``pending`` forever, and the run reported ``done`` with a
null exit_reason -- indistinguishable from a full run.

That is how three of the quodeq project's daily runs came to average only
their worst dimensions: the ones that never ran were security-adjacent
stragglers at the end of the order (usability, flexibility,
clean-architecture), all scoring higher than the ones that did run.
"""
from pathlib import Path

from quodeq.analysis.run_lifecycle import RunLifecycleContext
from quodeq.core.run.dimensions import DimState
from quodeq.data.fs.dimensions_state_store import read_dimensions, write_dim_state
from quodeq.data.fs.run_status_store import read_status


def _states(run_dir: Path) -> dict[str, str]:
    entries = read_dimensions(run_dir).get("dimensions", {})
    return {name: entry.get("state") for name, entry in entries.items()}


def test_clean_exit_marks_never_started_dimensions_incomplete(tmp_path: Path) -> None:
    with RunLifecycleContext(
        run_dir=tmp_path, job_id="j1",
        dimensions=["security", "usability", "flexibility"],
    ) as lifecycle:
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "security", DimState.DONE)
        lifecycle.transition_to_finalizing()

    states = _states(tmp_path)
    assert states["security"] == "done"
    assert states["usability"] == "incomplete"
    assert states["flexibility"] == "incomplete"


def test_run_with_unscored_dimensions_does_not_report_a_clean_done(tmp_path: Path) -> None:
    with RunLifecycleContext(
        run_dir=tmp_path, job_id="j1",
        dimensions=["security", "usability"],
    ) as lifecycle:
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "security", DimState.DONE)
        lifecycle.transition_to_finalizing()

    status = read_status(tmp_path)
    assert status is not None
    assert status["state"] == "done"
    # The run is over and a dimension never ran. Without a reason here the
    # History row and the trend read this exactly like a complete run.
    assert status["exit_reason"] == "incomplete_dimensions"


def test_fully_scored_run_stays_a_clean_done(tmp_path: Path) -> None:
    with RunLifecycleContext(
        run_dir=tmp_path, job_id="j1", dimensions=["security"],
    ) as lifecycle:
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "security", DimState.DONE)
        lifecycle.transition_to_finalizing()

    status = read_status(tmp_path)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] is None
    assert _states(tmp_path) == {"security": "done"}


def test_explicit_exit_reason_is_not_overwritten(tmp_path: Path) -> None:
    """A caller-supplied reason is more specific than 'some dims were skipped'."""
    with RunLifecycleContext(
        run_dir=tmp_path, job_id="j1", dimensions=["security", "usability"],
    ) as lifecycle:
        lifecycle.set_exit_reason("time_limit")
        lifecycle.transition_to_finalizing()

    status = read_status(tmp_path)
    assert status is not None
    assert status["exit_reason"] == "time_limit"
    assert _states(tmp_path)["usability"] == "incomplete"
