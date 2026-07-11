import json
import logging

logger = logging.getLogger(__name__)


def load_records(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not load %s: %s", path, exc)
        return []
