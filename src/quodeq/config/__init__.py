"""Configuration layer: path resolution, discipline detection, AI provider and
model selection, prompt templates, and standards fetching.

Also home to the ``*_env`` readers that keep ``quodeq.core`` and
``quodeq.analysis`` free of environment lookups. Nothing is re-exported here;
callers import the modules directly.
"""
