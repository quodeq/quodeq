"""Constants shared across the assistant package's top-level modules."""
from __future__ import annotations

# Positional decode()/encode() calls that don't already self-document via an
# encoding= keyword (worktree.py's git subprocess output).
ENCODING_UTF8 = "utf-8"

# ai_providers.json's "type" field: whether a provider's turn is driven over
# HTTP or a spawned CLI process (orchestrator.py). Mirrors api/_constants.py's
# CLIENT_TYPE_CLI (assistant may not import from api/); reconcile the two
# homes later.
PROVIDER_CLIENT_TYPE_CLI = "cli"
