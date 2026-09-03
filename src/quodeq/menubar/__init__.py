"""Built-in macOS menu bar icon for the Quodeq dashboard app.

Runs as its own detached subprocess of the same binary (``Quodeq --_menubar``
frozen, ``python -m quodeq.menubar`` in dev), toggled from Settings and
persisted in ~/.quodeq/menubar_state.json.
"""
