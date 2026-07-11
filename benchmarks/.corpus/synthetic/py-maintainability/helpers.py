def format_currency(amount: float) -> str:
    return f"{amount:.2f} EUR"


def region_label(region: str) -> str:
    return region.strip().upper()
