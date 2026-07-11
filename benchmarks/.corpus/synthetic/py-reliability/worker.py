import json


def process_queue(items: list[str]) -> list[dict]:
    results = []
    for item in items:
        try:
            results.append(json.loads(item))
        except:
            pass
    return results
