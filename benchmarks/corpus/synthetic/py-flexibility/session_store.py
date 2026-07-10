_SESSIONS: dict[str, dict] = {}


def save_session(session_id: str, data: dict) -> None:
    _SESSIONS[session_id] = data


def load_session(session_id: str) -> dict:
    return _SESSIONS.get(session_id, {})
