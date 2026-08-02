"""Deterministic requirement checkers -- pure logic, no I/O.

Some requirements in a standard are properties of the whole codebase rather
than of any single file: "dependencies point inward", "no transitive framework
dependencies in core layers". A per-file LLM pass cannot judge them, which is
why a third of the clean-architecture standard has never produced a judgment.

A checker answers one such requirement deterministically from static facts
(an import graph, a file list) and returns ordinary ``Judgment`` objects, so
everything downstream -- scoring, dismissal, the dashboard, SQL projection --
treats them like any other finding.

Reading the facts off disk is the data layer's job (``data/fs/import_graph``);
this package only decides what they mean.
"""
