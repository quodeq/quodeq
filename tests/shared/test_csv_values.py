"""split_csv: a comma-separated setting as its trimmed, non-empty items."""
from __future__ import annotations

from quodeq.shared.csv_values import split_csv


def test_items_are_trimmed_and_kept_in_order():
    assert split_csv(" b, a ,c") == ["b", "a", "c"]


def test_blank_items_are_dropped():
    assert split_csv(",a,, ,b,") == ["a", "b"]


def test_an_empty_string_has_no_items():
    assert split_csv("") == []
