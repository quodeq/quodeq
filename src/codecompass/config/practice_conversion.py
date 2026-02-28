import re


def parse_practice_markdown(markdown: str) -> dict:
    metadata = {}
    practices_index = []
    body = ""
    lines = markdown.splitlines()
    in_metadata = False
    in_index = False
    body_start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and re.match(r"## \\d+\\.", line):
            body_start = i
            break
        if line.strip() == "## Metadata":
            in_metadata = True
            in_index = False
            continue
        if line.strip() == "## Practices Index":
            in_index = True
            in_metadata = False
            continue
        if in_metadata and line.startswith("| ") and "Field" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                key = parts[0].lower().replace(" ", "_")
                value = parts[1]
                if key == "practices":
                    metadata["practice_count"] = int(value)
                else:
                    metadata[key] = value
        if in_index and line.startswith("| ") and "ID" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4:
                practices_index.append(
                    {
                        "id": parts[0],
                        "name": parts[1],
                        "section": parts[2],
                        "principle": parts[3],
                    }
                )
    if body_start is not None:
        body = "\n".join(lines[body_start:]).strip() + "\n"
    return {"metadata": metadata, "practices_index": practices_index, "body": body}
