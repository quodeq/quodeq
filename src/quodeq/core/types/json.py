"""Type aliases for raw JSON at parsing boundaries only."""
from __future__ import annotations

from typing import Union

JsonValue = Union[str, int, float, bool, None, list["JsonValue"], dict[str, "JsonValue"]]
JsonObject = dict[str, JsonValue]
