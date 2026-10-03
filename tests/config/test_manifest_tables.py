"""toml_table and lowered_keys: the two steps every TOML/JSON manifest parser shares."""
from __future__ import annotations

from quodeq.config.manifest_tables import lowered_keys, toml_table


def test_toml_table_parses_a_document():
    assert toml_table('[deps]\nFoo = "1"\n') == {"deps": {"Foo": "1"}}


def test_toml_table_is_none_for_broken_toml():
    assert toml_table("[deps\n") is None


def test_lowered_keys_collects_mapping_keys_under_each_key():
    table = {"a": {"Foo": 1, "bar": 2}, "b": {"BAZ": 3}, "c": {"skip": 4}}
    assert lowered_keys(table, ("a", "b")) == {"foo", "bar", "baz"}


def test_lowered_keys_ignores_missing_keys_non_mappings_and_non_string_keys():
    table = {"a": ["Foo"], "b": "Bar", "c": {1: "x", "Ok": "y"}}
    assert lowered_keys(table, ("a", "b", "c", "missing")) == {"ok"}
