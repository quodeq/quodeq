from __future__ import annotations

def list_practice_files(practices_repo: object, discipline: str) -> list[str]:
    return list(practices_repo.list_topics(discipline))


def resolve_practice(index: int, practices_repo: object, discipline: str) -> str:
    files = list_practice_files(practices_repo, discipline)
    if index < 1 or index > len(files):
        raise ValueError(f"Practice index {index} out of range (1-{len(files)})")
    return files[index - 1]


def _title_case_from_filename(filename: str) -> str:
    words = filename.replace("_", " ").split()
    return " ".join(word[:1].upper() + word[1:].lower() for word in words if word)


def extract_practice_metadata(practices_repo: object, discipline: str, topic: str) -> tuple[str, str]:
    data = practices_repo.get_practice(discipline, topic)
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}

    topic_value = metadata.get("topic") or ""
    language_value = metadata.get("language") or ""

    if not topic_value:
        topic_value = _title_case_from_filename(topic)

    if not language_value:
        # Discipline registry not yet ported; default to text
        language_value = "text"

    return str(topic_value), str(language_value)
