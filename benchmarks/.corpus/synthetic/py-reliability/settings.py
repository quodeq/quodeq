import json


def load_port(raw: str) -> int:
    try:
        return int(json.loads(raw)["port"])
    except Exception:
        return 8080
