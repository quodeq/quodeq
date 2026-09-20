"""Environment-based configuration for evidence enrichment.

Core (``quodeq.core.evidence``) never reads the environment; outer layers
resolve these values here and pass them down.
"""
from __future__ import annotations

import os

from quodeq.core.evidence.refs import CWE_URL_TEMPLATE_DEFAULT


def cwe_url_template(env: dict[str, str] | None = None) -> str:
    """Return the CWE reference URL template, honoring QUODEQ_CWE_URL_TEMPLATE.

    Overridable for offline or internal deployments; unset means the packaged
    default (the same one core falls back to when no template is passed).
    """
    return (os.environ if env is None else env).get("QUODEQ_CWE_URL_TEMPLATE", CWE_URL_TEMPLATE_DEFAULT)
