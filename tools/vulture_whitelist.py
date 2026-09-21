"""Whitelist for tools/check_dead_code.py (vulture).

Vulture sees only static references, so a name reached dynamically looks
unused. Reference such a name here and vulture counts it as used.

Entries are allowed ONLY for names that really are reached dynamically
(pytest fixtures, Flask routes, ABC hooks, __all__ re-exports) and each
one carries a one-line reason. A name that is simply dead is deleted, not
whitelisted; a name that a grep still finds is not dead.

Empty on purpose: nothing in src/quodeq needs an entry today.
"""
