"""JobStatus wire values, parsing, the finished set and the external-job-id helpers."""
import json

import pytest

from quodeq.core.run.job_status import (
    EXTERNAL_JOB_PREFIX,
    JOB_FINISHED,
    JobStatus,
    external_job_id,
    is_external_job_id,
    parse_job_status,
    strip_external_prefix,
)


def test_values_match_the_persisted_spellings():
    assert [m.value for m in JobStatus] == ["running", "done", "failed", "cancelled", "lost"]
    assert json.dumps({"status": JobStatus.DONE}) == '{"status": "done"}'


@pytest.mark.parametrize("raw", [m.value for m in JobStatus])
def test_parse_job_status_accepts_every_member_value(raw):
    assert parse_job_status(raw) is JobStatus(raw)


def test_parse_job_status_ignores_case_and_whitespace():
    assert parse_job_status("  Done ") is JobStatus.DONE


@pytest.mark.parametrize("raw", ["completed", "bogus", "", None])
def test_parse_job_status_rejects_unknown(raw):
    with pytest.raises(ValueError, match="unknown job status"):
        parse_job_status(raw)


def test_finished_set_excludes_lost():
    """LOST means the tracking thread died, not that the subprocess did --
    JOB_FINISHED is the "actually over" set callers should use to decide
    whether to stop tailing/report complete."""
    assert JOB_FINISHED == frozenset(
        {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}
    )


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
