"""Path-jailed, read-only access to the analyzed repository."""
from __future__ import annotations

from pathlib import Path

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec

_MAX_FILE_BYTES = 65_536
_MAX_DIR_ENTRIES = 500
_DENY_BASENAMES = (".env", "id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc")
_DENY_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")


def _jail(ctx: ToolContext, rel_path: str) -> Path:
    if ctx.repo_root is None:
        raise ToolError("no analyzed repository attached to this session")
    root = ctx.repo_root.resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise ToolError("path escapes the analyzed repository")
    name = target.name.lower()
    if name.startswith(_DENY_BASENAMES) or name.endswith(_DENY_SUFFIXES):
        raise ToolError("path is on the secrets denylist")
    if target.name == ".git" or ".git" in {p.name for p in target.parents}:
        raise ToolError("path is inside the .git directory")
    return target


def _read_repo_file(ctx: ToolContext, path: str) -> dict:
    target = _jail(ctx, path)
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    with target.open("rb") as fh:
        raw = fh.read(_MAX_FILE_BYTES + 1)
    if b"\x00" in raw[:1024]:
        raise ToolError("binary file")
    truncated = len(raw) > _MAX_FILE_BYTES
    text = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
    return {"path": path, "content": text, "truncated": truncated}


def _list_repo_dir(ctx: ToolContext, path: str = ".") -> dict:
    target = _jail(ctx, path)
    if not target.is_dir():
        raise ToolError(f"not a directory: {path}")
    entries = []
    for child in sorted(target.iterdir())[:_MAX_DIR_ENTRIES]:
        entries.append(child.name + "/" if child.is_dir() else child.name)
    return {"path": path, "entries": entries}


def register_repo_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "read_repo_file", "Read one file from the analyzed repository (read-only).",
        {"type": "object", "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        lambda **kw: _read_repo_file(ctx, **kw)))
    registry.register(ToolSpec(
        "list_repo_dir", "List entries of a directory in the analyzed repository.",
        {"type": "object", "properties": {"path": {"type": "string"}}},
        lambda **kw: _list_repo_dir(ctx, **kw)))
