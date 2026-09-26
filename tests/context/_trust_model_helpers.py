"""project-profile.json writer shared by the test_trust_model* siblings."""
from __future__ import annotations

import json

from quodeq.context.trust_model import PROFILE_RELPATH


def _write_profile(root, payload):
    path = root / PROFILE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
