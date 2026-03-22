"""Tests for adaptive subagent runner functions."""
from __future__ import annotations

from quodeq.analysis.subagents.runner import _compute_files_per_agent


class TestComputeFilesPerAgent:
    def test_small_project_no_rotation(self):
        assert _compute_files_per_agent(20) == 20

    def test_boundary_50(self):
        assert _compute_files_per_agent(50) == 50

    def test_medium_project(self):
        assert _compute_files_per_agent(100) == 50

    def test_boundary_200(self):
        assert _compute_files_per_agent(200) == 50

    def test_large_project(self):
        assert _compute_files_per_agent(500) == 75

    def test_boundary_1000(self):
        assert _compute_files_per_agent(1000) == 75

    def test_very_large_project(self):
        assert _compute_files_per_agent(5000) == 100

    def test_minimum_1(self):
        assert _compute_files_per_agent(1) == 1

    def test_zero_files(self):
        assert _compute_files_per_agent(0) == 0
