"""JSON codec for event-log entries (events.jsonl / actions.jsonl).

The core event dataclasses know nothing about serialization; the wire format
lives here, in the data layer. The encoder emits exactly what pydantic v2's
``model_dump_json`` produced before the entities became plain dataclasses --
compact separators, ``null`` for unset optionals, UUIDs as strings, UTC
datetimes with a trailing ``Z``, enums by value -- so existing log files and
new lines stay byte-compatible.
"""
from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
from typing import Any
from uuid import UUID

from quodeq.core.events.models import (
    EVENT_MODEL_MAP,
    PAYLOAD_MODEL_MAP,
    BaseEvent,
    EventType,
)
from quodeq.core.types.req_ref import ReqRef


class EventDecodeError(ValueError):
    """A stored event dict does not fit its event model."""


# Payload dataclass per event model, derived from the two per-EventType maps.
_PAYLOAD_CLS_BY_MODEL: dict[type[BaseEvent], type] = {
    model_cls: PAYLOAD_MODEL_MAP[event_type]
    for event_type, model_cls in EVENT_MODEL_MAP.items()
}


def event_to_json(event: BaseEvent) -> str:
    """Serialize an event to a single JSON line (no trailing newline)."""
    return json.dumps(
        asdict(event), separators=(",", ":"), ensure_ascii=False,
        default=_json_default,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        text = value.isoformat()
        # pydantic wrote UTC as a trailing "Z"; keep new lines identical.
        return text[:-6] + "Z" if text.endswith("+00:00") else text
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def event_from_dict(model_cls: type[BaseEvent], raw: dict) -> BaseEvent:
    """Decode a stored event dict into *model_cls*.

    Unknown keys are ignored (as pydantic did); missing keys with defaults
    fall back to those defaults. Raises :class:`EventDecodeError` when the
    dict does not fit the model.
    """
    if not isinstance(raw, dict):
        raise EventDecodeError(f"event must be a JSON object, got {type(raw).__name__}")
    try:
        kwargs: dict[str, Any] = {}
        if "event_id" in raw:
            kwargs["event_id"] = UUID(str(raw["event_id"]))
        if "timestamp" in raw:
            kwargs["timestamp"] = _parse_timestamp(raw["timestamp"])
        if "event_type" in raw:
            kwargs["event_type"] = EventType(raw["event_type"])
        if "payload" in raw:
            kwargs["payload"] = _decode_payload(model_cls, raw["payload"])
        return model_cls(**kwargs)
    except EventDecodeError:
        raise
    except (TypeError, ValueError) as exc:
        raise EventDecodeError(str(exc)) from exc


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _decode_payload(model_cls: type[BaseEvent], raw_payload: Any) -> Any:
    payload_cls = _PAYLOAD_CLS_BY_MODEL.get(model_cls)
    if payload_cls is None:
        raise EventDecodeError(f"no payload class registered for {model_cls.__name__}")
    if not isinstance(raw_payload, dict):
        raise EventDecodeError(
            f"payload must be a JSON object, got {type(raw_payload).__name__}"
        )
    field_names = {f.name for f in fields(payload_cls)}
    kwargs = {k: v for k, v in raw_payload.items() if k in field_names}
    if "req_refs" in kwargs:
        kwargs["req_refs"] = _decode_req_refs(kwargs["req_refs"])
    return payload_cls(**kwargs)


def _coerce_legacy_req_refs(value: Any) -> Any:
    """Accept the legacy bare-string format for ``req_refs``.

    Historical events.jsonl files stored req_refs as a list of bare
    strings (e.g. ``["CWE-89", "CISQ"]``) before the ReqRef struct was
    introduced. Strict validation rejected the whole event, which made
    EventLogReader silently skip it — producing empty grade tables and
    nonsensical scores for any pre-refactor run.

    Coerce strings to ``ReqRef(label=<string>, url="")`` so legacy events
    round-trip cleanly. The empty url means the UI's filterValidRefs()
    drops them from links (it requires http(s)://), which is the right
    behaviour: there is no URL to recover.
    """
    if not isinstance(value, list):
        return value
    coerced = []
    for item in value:
        if isinstance(item, str):
            coerced.append(ReqRef(label=item, url=""))
        else:
            coerced.append(item)
    return coerced


def _decode_req_refs(value: Any) -> list[ReqRef]:
    value = _coerce_legacy_req_refs(value)
    if not isinstance(value, list):
        raise EventDecodeError(f"req_refs must be a list, got {type(value).__name__}")
    refs: list[ReqRef] = []
    for item in value:
        if isinstance(item, ReqRef):
            refs.append(item)
        elif isinstance(item, dict):
            try:
                refs.append(ReqRef(label=item["label"], url=item["url"]))
            except KeyError as exc:
                raise EventDecodeError(f"req_refs entry missing key {exc}") from exc
        else:
            raise EventDecodeError(
                f"req_refs entry must be a string or object, got {type(item).__name__}"
            )
    return refs
