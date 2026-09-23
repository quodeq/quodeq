"""JobStatus wire values, the terminal set and the external-job-id helpers."""
import json

from quodeq.core.run.job_status import (
    EXTERNAL_JOB_PREFIX,
    JOB_FINISHED,
    JOB_TERMINAL,
    JobStatus,
    external_job_id,
    is_external_job_id,
    strip_external_prefix,
)


def test_values_match_the_persisted_spellings():
    assert [m.value for m in JobStatus] == ["running", "done", "failed", "cancelled", "lost"]
    assert json.dumps({"status": JobStatus.DONE}) == '{"status": "done"}'


def test_terminal_set():
    assert JOB_TERMINAL == frozenset(
        {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.LOST}
    )


def test_finished_set_excludes_lost():
    """LOST means the tracking thread died, not that the subprocess did --
    JOB_FINISHED is the "actually over" set callers should use to decide
    whether to stop tailing/report complete."""
    assert JOB_FINISHED == frozenset(
        {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}
    )
    assert JobStatus.LOST not in JOB_FINISHED
    assert JobStatus.LOST in JOB_TERMINAL


def test_external_prefix_helpers():
    assert EXTERNAL_JOB_PREFIX == "ext-"
    assert is_external_job_id("ext-abc")
    assert not is_external_job_id("abc")
    assert strip_external_prefix("ext-abc") == "abc"
    assert strip_external_prefix("abc") == "abc"


def test_external_job_id_is_the_inverse_of_strip_external_prefix():
    assert external_job_id("abc") == "ext-abc"
    assert strip_external_prefix(external_job_id("abc")) == "abc"
    assert is_external_job_id(external_job_id("abc"))
