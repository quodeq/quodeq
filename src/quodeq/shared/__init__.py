"""Cross-cutting utilities and infrastructure shared across all bounded contexts.

Helpers whose real home is a private submodule (``_env``, ``_env_ai``,
``_diff``) are re-exported here so callers import a public name from the
package instead of reaching into the private module.
"""
from quodeq.shared._diff import show_diff
from quodeq.shared._env import env_int, get_asvs_url
from quodeq.shared._env_ai import get_ai_provider

__all__ = ["env_int", "get_ai_provider", "get_asvs_url", "show_diff"]
