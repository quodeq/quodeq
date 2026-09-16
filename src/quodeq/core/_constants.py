"""Core-wide constants. ``core`` may not import ``shared``, and this leaf imports nothing."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

FULL_CONFIDENCE = 100  # a finding the scanner is fully sure of; downweights subtract from this
