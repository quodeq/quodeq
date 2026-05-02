import json
from pathlib import Path

import pytest

from quodeq.context.precedent import fingerprint, load_precedent_fingerprints


def test_fingerprint_is_stable_for_same_inputs():
    a = fingerprint("S-CON-1", "password = 'secret'")
    b = fingerprint("S-CON-1", "password = 'secret'")
    assert a == b
    assert a is not None


def test_fingerprint_normalizes_whitespace():
    a = fingerprint("S-CON-1", "password = 'secret'")
    b = fingerprint("S-CON-1", "  password = 'secret'  ")
    c = fingerprint("S-CON-1", "password\t=\t'secret'")
    assert a == b == c


def test_fingerprint_changes_with_req():
    a = fingerprint("S-CON-1", "x = 1")
    b = fingerprint("S-CON-2", "x = 1")
    assert a != b


def test_fingerprint_changes_with_snippet():
    a = fingerprint("S-CON-1", "x = 1")
    b = fingerprint("S-CON-1", "y = 1")
    assert a != b


def test_fingerprint_returns_none_for_empty_inputs():
    assert fingerprint(None, None) is None
    assert fingerprint("", "") is None
    assert fingerprint("  ", "  ") is None


def test_fingerprint_works_with_only_req():
    assert fingerprint("S-CON-1", None) is not None
    assert fingerprint("S-CON-1", "") is not None


def test_fingerprint_strips_trailing_punctuation():
    a = fingerprint("R", "do_it()")
    b = fingerprint("R", "do_it();")
    c = fingerprint("R", "do_it().")
    assert a == b == c


def test_load_returns_empty_for_missing_dir(tmp_path: Path):
    assert load_precedent_fingerprints(tmp_path / "missing") == set()


def test_load_returns_empty_for_missing_file(tmp_path: Path):
    assert load_precedent_fingerprints(tmp_path) == set()


def test_load_returns_fingerprints_for_each_entry(tmp_path: Path):
    entries = [
        {"req": "S-CON-1", "snippet": "password = 'secret'"},
        {"req": "M-MOD-2", "snippet": "def foo(): pass"},
    ]
    (tmp_path / "dismissed.json").write_text(json.dumps(entries))
    out = load_precedent_fingerprints(tmp_path)
    assert len(out) == 2
    assert fingerprint("S-CON-1", "password = 'secret'") in out
    assert fingerprint("M-MOD-2", "def foo(): pass") in out


def test_load_skips_blank_entries(tmp_path: Path):
    entries = [
        {"req": "", "snippet": ""},
        {"req": "M-MOD-2", "snippet": "def foo(): pass"},
        "not a dict",
        {},
    ]
    (tmp_path / "dismissed.json").write_text(json.dumps(entries))
    out = load_precedent_fingerprints(tmp_path)
    assert out == {fingerprint("M-MOD-2", "def foo(): pass")}


def test_load_handles_malformed_json(tmp_path: Path):
    (tmp_path / "dismissed.json").write_text("{not valid json")
    assert load_precedent_fingerprints(tmp_path) == set()


def test_load_handles_non_list_root(tmp_path: Path):
    (tmp_path / "dismissed.json").write_text('{"oops": "object instead of list"}')
    assert load_precedent_fingerprints(tmp_path) == set()
