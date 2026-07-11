import requests


def fetch_status(url: str) -> int:
    response = requests.get(url)
    return response.status_code


def fetch_until_ok(url: str) -> int:
    while True:
        code = fetch_status(url)
        if code == 200:
            return code
