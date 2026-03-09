from quodeq.config.paths import ConfigPaths
from quodeq.logging import log_error


def validate_new_discipline(name: str, language: str, category: str) -> int:
    if not name or not language:
        log_error(
            "Usage: add-discipline <name> <language> [--category=<backend|frontend|mobile|infra>]"
        )
        return 1
    if category not in {"backend", "frontend", "mobile", "infra"}:
        log_error(f"Invalid category '{category}'. Must be: backend, frontend, mobile, or infra")
        return 1
    return 0


def get_discipline_language(name: str, paths: ConfigPaths) -> str | None:
    conf = paths.root / "config" / "disciplines.conf"
    if not conf.exists():
        return None
    current = None
    for line in conf.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            continue
        if current == name and line.startswith("language="):
            return line.split("=", 1)[1].strip()
    return None
