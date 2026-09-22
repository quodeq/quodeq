"""Unit tests for the Gemfile, mix.exs, pubspec.yaml and Julia Project.toml parsers."""
from __future__ import annotations

import pytest

from quodeq.config._dependency_parsers import (
    has_gemfile_gem,
    has_julia_dependency,
    has_mix_dep,
    has_pubspec_dependency,
)


# --- Gemfile -----------------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    ('gem "rails"\n', "rails", True),
    ("gem 'sinatra'\n", "sinatra", True),
    ('gem "rails", "~> 7.1"\n', "rails", True),
    # Comment-only mention does NOT match.
    ('# we used to use rails\ngem "rack"\n', "rails", False),
    # Derived gem name doesn't match the parent name (exact match).
    ('gem "rails-controller-testing"\n', "rails", False),
    ('gem "rails-controller-testing"\n', "rails-controller-testing", True),
    # Multiple gems.
    ('gem "rack"\ngem "sinatra"\n', "sinatra", True),
])
def test_gemfile(body: str, needle: str, expected: bool) -> None:
    assert has_gemfile_gem(body, needle) is expected


# --- mix.exs -----------------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    ('def deps, do: [{:phoenix, "~> 1.7"}]\n', "phoenix", True),
    ('def deps, do: [{:phoenix, "~> 1.7"}, {:ecto, "~> 3.0"}]\n', "ecto", True),
    # Only declared as comment — no match.
    ('# was using phoenix\ndef deps, do: [{:plug, "~> 1.0"}]\n', "phoenix", False),
    # Underscored atom names allowed.
    ('def deps, do: [{:tesla_otel, "~> 1.0"}]\n', "tesla_otel", True),
])
def test_mix_exs(body: str, needle: str, expected: bool) -> None:
    assert has_mix_dep(body, needle) is expected


# --- pubspec.yaml ------------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    (
        "name: x\ndependencies:\n  flutter:\n    sdk: flutter\n",
        "flutter", True,
    ),
    (
        "name: x\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n",
        "flutter_test", True,
    ),
    # description containing 'flutter' must NOT match.
    (
        'name: x\ndescription: "a flutter-style framework"\ndependencies:\n  http: ^1.0.0\n',
        "flutter", False,
    ),
    # Comments stripped.
    (
        "# flutter is great\nname: x\ndependencies:\n  http: ^1.0.0\n",
        "flutter", False,
    ),
    # Nested values (sdk: flutter under flutter:) do NOT contribute to matches at outer level.
    (
        "name: x\ndependencies:\n  http:\n    version: ^1.0.0\n",
        "http", True,
    ),
])
def test_pubspec(body: str, needle: str, expected: bool) -> None:
    assert has_pubspec_dependency(body, needle) is expected


# --- Project.toml (Julia) ----------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    (
        'name = "X"\n[deps]\nDataFrames = "00000000-0000-0000-0000-000000000000"\n',
        "DataFrames", True,
    ),
    (
        'name = "X"\n[deps]\nDataFrames = "00000000-0000-0000-0000-000000000000"\n',
        "Plots", False,
    ),
    # Case-insensitive lookup.
    (
        'name = "X"\n[deps]\nDataFrames = "00000000-0000-0000-0000-000000000000"\n',
        "dataframes", True,
    ),
])
def test_julia_project_toml(body: str, needle: str, expected: bool) -> None:
    assert has_julia_dependency(body, needle) is expected
