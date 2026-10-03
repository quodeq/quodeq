"""Tests for the file-level test sharding the Windows CI legs use."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests._sharding import parse_shard, select_shard


@dataclass(frozen=True)
class _Item:
    nodeid: str


def _items(*nodeids: str) -> list[_Item]:
    return [_Item(n) for n in nodeids]


_FILES = [f"tests/{d}/test_{n}.py" for d in ("api", "data", "services", "tools") for n in range(25)]
_SUITE = _items(*(f"{f}::test_{k}" for f in _FILES for k in range(3)))


class TestParseShard:
    @pytest.mark.parametrize("raw", [None, "", "1/1"])
    def test_unset_or_whole_means_the_single_shard(self, raw: str | None):
        assert parse_shard(raw) == (1, 1)

    def test_reads_index_and_total(self):
        assert parse_shard("2/2") == (2, 2)

    @pytest.mark.parametrize("raw", ["2", "0/2", "3/2", "a/b", "1/0", "1/2/3"])
    def test_malformed_spec_names_the_variable(self, raw: str):
        with pytest.raises(ValueError, match="QUODEQ_TEST_SHARD"):
            parse_shard(raw)


class TestSelectShard:
    def test_the_single_shard_keeps_every_item_in_order(self):
        kept, dropped = select_shard(_SUITE, 1, 1)
        assert kept == _SUITE
        assert dropped == []

    def test_two_shards_partition_the_suite_exactly(self):
        kept_1, dropped_1 = select_shard(_SUITE, 1, 2)
        kept_2, dropped_2 = select_shard(_SUITE, 2, 2)
        assert sorted(kept_1 + kept_2, key=lambda i: i.nodeid) == sorted(_SUITE, key=lambda i: i.nodeid)
        assert not set(kept_1) & set(kept_2)
        assert set(dropped_1) == set(kept_2)
        assert set(dropped_2) == set(kept_1)

    def test_every_shard_gets_a_fair_share(self):
        sizes = [len(select_shard(_SUITE, i, 3)[0]) for i in (1, 2, 3)]
        assert all(size > 0 for size in sizes)
        assert max(sizes) - min(sizes) < len(_SUITE) // 4

    def test_a_file_never_straddles_shards(self):
        for index in (1, 2):
            kept, dropped = select_shard(_SUITE, index, 2)
            kept_files = {i.nodeid.split("::")[0] for i in kept}
            dropped_files = {i.nodeid.split("::")[0] for i in dropped}
            assert not kept_files & dropped_files

    def test_assignment_is_stable_across_runs(self):
        first = [i.nodeid for i in select_shard(_SUITE, 1, 2)[0]]
        second = [i.nodeid for i in select_shard(list(reversed(_SUITE)), 1, 2)[0]]
        assert sorted(first) == sorted(second)

    def test_keeps_collection_order_within_a_shard(self):
        kept, _ = select_shard(_SUITE, 2, 2)
        positions = [_SUITE.index(i) for i in kept]
        assert positions == sorted(positions)
