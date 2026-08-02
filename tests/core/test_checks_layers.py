"""Inner-layer detection: which files hold the code that must stay pure.

A deterministic checker can only judge a project whose layers it can name.
Detection is by convention (``domain/``, ``entities/``, ``usecases/``,
``core/``, ...) because the alternative -- guessing from import shape -- is
how you get an architecture report full of noise about a project that never
claimed to be layered.

The fail-soft rule matters more than the name table: a project with no
recognisable inner layer yields NO findings, not a clean bill of health and
not a wall of violations. Silence is the honest answer when we cannot see.
"""
from __future__ import annotations

from quodeq.core.checks.layers import inner_layer_files, is_inner_layer_path


class TestIsInnerLayerPath:
    def test_conventional_inner_directories(self):
        for path in (
            "src/domain/order.py",
            "src/entities/user.py",
            "app/usecases/place_order.py",
            "app/use_cases/place_order.py",
            "src/quodeq/core/evidence/model.py",
            "lib/interactors/checkout.rb",
        ):
            assert is_inner_layer_path(path), path

    def test_outer_directories_are_not_inner(self):
        for path in (
            "src/api/routes.py",
            "src/infrastructure/db.py",
            "src/adapters/sql_repo.py",
            "src/ui/components/Button.jsx",
            "main.py",
        ):
            assert not is_inner_layer_path(path), path

    def test_matching_is_on_a_whole_path_segment(self):
        """``core_utils/`` is not ``core/`` -- substring matching invents layers."""
        assert not is_inner_layer_path("src/core_utils/helpers.py")
        assert not is_inner_layer_path("src/domainservices/x.py")

    def test_ambiguous_names_are_not_inner(self):
        """``models/`` is the ORM directory as often as the domain one."""
        assert not is_inner_layer_path("src/models/user.py")

    def test_windows_separators_resolve(self):
        assert is_inner_layer_path("src\\domain\\order.py")

    def test_blank_input(self):
        assert not is_inner_layer_path("")


class TestInnerLayerFiles:
    def test_selects_only_inner_paths(self):
        paths = ["src/domain/a.py", "src/api/b.py", "src/entities/c.py"]
        assert inner_layer_files(paths) == frozenset({"src/domain/a.py", "src/entities/c.py"})

    def test_no_inner_layer_yields_empty(self):
        """The fail-soft gate: an unlayered project is not judged."""
        assert inner_layer_files(["main.py", "utils.py", "server.py"]) == frozenset()
