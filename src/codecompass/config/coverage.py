def parse_coverage_percent(value: str) -> int:
    return int(value.strip().rstrip("%"))


def coverage_percent(value: str) -> int:
    if "/" in value:
        num, denom = value.split("/", 1)
        return int(round((int(num) / int(denom)) * 100))
    return parse_coverage_percent(value)
