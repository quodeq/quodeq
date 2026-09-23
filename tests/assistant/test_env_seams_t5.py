"""Assistant env seams: an injected mapping is the only source read.

Each seam is checked twice -- with a value injected, and with an injected
``{}`` while the process environment carries a different value, which must
be ignored.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.assistant.adapters._cli_spawn import build_chat_env
from quodeq.assistant.skills import cached_skills, load_skills, skills_directory
from quodeq.assistant.worktree import _DEFAULT_WORKTREE_TTL_H, worktree_ttl_hours, worktrees_base


class TestSkillsDirectory:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert skills_directory({"QUODEQ_ASSISTANT_SKILLS_DIR": str(injected)}) == injected

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(tmp_path / "from-process"))
        assert skills_directory({}).name == "skills"

    def test_is_read_at_call_time_not_import_time(self, monkeypatch, tmp_path):
        """The old module constant froze this at first import; it no longer does."""
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(tmp_path))
        assert skills_directory() == tmp_path


_SKILL_FILE = """---
name: injected-skill
description: only present in the injected directory
---
body
"""


class TestLoadSkillsTakesEnv:
    def _pack(self, tmp_path) -> Path:
        directory = tmp_path / "pack"
        directory.mkdir()
        (directory / "injected.md").write_text(_SKILL_FILE, encoding="utf-8")
        return directory

    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(tmp_path / "from-process"))
        pack = self._pack(tmp_path)
        assert "injected-skill" in load_skills(env={"QUODEQ_ASSISTANT_SKILLS_DIR": str(pack)})

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(self._pack(tmp_path)))
        assert "injected-skill" not in load_skills(env={})

    def test_cached_skills_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(tmp_path / "from-process"))
        pack = self._pack(tmp_path)
        assert "injected-skill" in cached_skills(env={"QUODEQ_ASSISTANT_SKILLS_DIR": str(pack)})

    def test_cached_skills_with_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_ASSISTANT_SKILLS_DIR", str(self._pack(tmp_path)))
        assert "injected-skill" not in cached_skills(env={})


class TestWorktreeTtlHours:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_ASSISTANT_WORKTREE_TTL_H", "5")
        assert worktree_ttl_hours({"QUODEQ_ASSISTANT_WORKTREE_TTL_H": "11"}) == 11

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_ASSISTANT_WORKTREE_TTL_H", "5")
        assert worktree_ttl_hours({}) == _DEFAULT_WORKTREE_TTL_H


class TestWorktreesBase:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_WORKTREES_DIR", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert worktrees_base({"QUODEQ_WORKTREES_DIR": str(injected)}) == injected

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_WORKTREES_DIR", str(tmp_path / "from-process"))
        assert worktrees_base({}) == Path.home() / ".quodeq" / "worktrees"


class TestBuildChatEnv:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("PATH", "/from-process")
        assert build_chat_env({"PATH": "/from-env"})["PATH"] == "/from-env"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("PATH", "/from-process")
        assert build_chat_env({}) == {}
