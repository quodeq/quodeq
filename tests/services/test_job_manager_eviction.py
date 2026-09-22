"""Tests for jobs.py: JobManager completed-job eviction (cap and oldest-first order)."""

from __future__ import annotations


from quodeq.services._job_model import InMemoryJobStore, Job
from quodeq.services.jobs import JobManager


# ---------------------------------------------------------------------------
# _evict_completed_jobs
# ---------------------------------------------------------------------------


class TestEvictCompletedJobs:
    def test_evicts_excess(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        from quodeq.services._job_model import _MAX_COMPLETED_JOBS
        # Add more than _MAX_COMPLETED_JOBS done jobs
        for i in range(_MAX_COMPLETED_JOBS + 5):
            store.put(Job(f"j{i}", "done", [], "now", "later", 0))
        mgr._evict_completed_jobs()
        remaining = store.list()
        assert len(remaining) == _MAX_COMPLETED_JOBS

    def test_running_not_evicted(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        store.put(Job("running1", "running", [], "now", None, None))
        store.put(Job("done1", "done", [], "now", "later", 0))
        mgr._evict_completed_jobs()
        assert store.get("running1") is not None


class TestEvictionOrder:
    def test_evicts_oldest_completed_first(self):
        """Eviction beyond _MAX_COMPLETED_JOBS must drop the OLDEST jobs.

        The victims used to be taken in store-iteration order, so a store
        wedged with old junk (crash leftovers, test pollution) could evict
        the user's newest real runs while the junk survived.
        """
        from quodeq.services.jobs import _MAX_COMPLETED_JOBS

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        total = _MAX_COMPLETED_JOBS + 3
        # Insert NEWEST first so naive iteration-order eviction picks the
        # newest as victims and the test goes red.
        for i in reversed(range(total)):
            store.put(Job(
                f"j{i:03d}", "done", ["echo"],
                "2026-01-01T00:00:00+00:00",
                f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}+00:00", 0,
            ))
        mgr._evict_completed_jobs()
        remaining = {j.job_id for j in store.list()}
        assert len(remaining) == _MAX_COMPLETED_JOBS
        # j000..j002 have the oldest ended_at values and must be the victims.
        assert "j000" not in remaining
        assert "j001" not in remaining
        assert "j002" not in remaining
        assert f"j{total - 1:03d}" in remaining
