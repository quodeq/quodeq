"""Mapper functions for plugin-related dataclasses."""

from __future__ import annotations

from quodeq.core.types.plugin import PluginDimension, PluginInfo

from ._mapper_helpers import (
    get_int,
    get_opt_str,
    require_str,
    get_str_list,
)


def parse_plugin_dimension(raw: dict[str, object]) -> PluginDimension:
    pid = require_str(raw, "id", "PluginDimension")
    return PluginDimension(
        id=pid,
        weight=get_int(raw, "weight", 1),
        iso_25010=get_opt_str(raw.get("iso_25010")),
    )


def parse_plugin_info(raw: dict[str, object]) -> PluginInfo:
    pid = require_str(raw, "id", "PluginInfo")
    name = require_str(raw, "name", "PluginInfo")

    dims_raw = raw.get("dimensions")
    dims: list[PluginDimension] = []
    if isinstance(dims_raw, list):
        dims = [parse_plugin_dimension(d) for d in dims_raw if isinstance(d, dict)]

    return PluginInfo(
        id=pid,
        name=name,
        extensions=get_str_list(raw, "extensions"),
        dimensions=dims,
    )
