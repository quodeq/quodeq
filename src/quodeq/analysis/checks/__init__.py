"""Deterministic checkers, wired into an evaluation run.

``core/checks`` holds the pure judgment logic and ``data/fs/import_graph``
reads the facts off disk. This package is the seam between them and the
pipeline: it resolves which checkers a dimension's standard asked for, runs
them, and merges the results into the run's evidence.
"""
