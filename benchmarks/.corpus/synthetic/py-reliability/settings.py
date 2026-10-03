import json
import logging

log = logging.getLogger(__name__)


def load_port(raw: str) -> int:
    try:
        return int(json.loads(raw)["port"])
    except Exception:
        log.warning("bad port config, using 8080", exc_info=True)
        return 8080
