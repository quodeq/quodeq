"""Tests for resource_sampler.py — except breadth broadening (#515).

The sampler loop's bare `except (OSError, ValueError)` must be broadened to
`except Exception` so a bad tick (e.g. RuntimeError) doesn't kill the thread.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

from quodeq.shared.resource_sampler import ResourceSampler


class TestSamplerLoopBreadth:
    def test_unexpected_exception_does_not_terminate_loop(self):
        """#515 — an exception not in (OSError, ValueError) must not kill the sampler thread.

        Before the fix, RuntimeError would propagate out of the loop and the thread would die.
        After the fix, the loop continues and the thread stays alive past the first tick.
        """
        tick_count = [0]
        errors_seen = [0]

        def _bad_sample_once():
            tick_count[0] += 1
            if tick_count[0] == 1:
                raise RuntimeError("unexpected bad tick")
            return "ok"

        sampler = ResourceSampler(interval_s=0.05)

        with patch.object(sampler, "sample_once", side_effect=_bad_sample_once):
            sampler.start()
            # Wait long enough for at least 2 ticks
            time.sleep(0.3)
            sampler.stop()

        # Thread must have continued past the first (bad) tick
        assert tick_count[0] >= 2, (
            f"Sampler thread died after bad tick — only {tick_count[0]} tick(s) observed"
        )

    def test_oserror_does_not_terminate_loop(self):
        """Original OSError handling still works after broadening."""
        tick_count = [0]

        def _oserror_sample():
            tick_count[0] += 1
            if tick_count[0] == 1:
                raise OSError("proc unavailable")
            return "ok"

        sampler = ResourceSampler(interval_s=0.05)

        with patch.object(sampler, "sample_once", side_effect=_oserror_sample):
            sampler.start()
            time.sleep(0.3)
            sampler.stop()

        assert tick_count[0] >= 2
