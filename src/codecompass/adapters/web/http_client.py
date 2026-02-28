from dataclasses import dataclass
import json
from urllib import request


@dataclass(frozen=True)
class HttpResponse:
    status: int
    data: dict


class HttpClient:
    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return HttpResponse(resp.status, payload)
        except request.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8")) if exc.fp else {"error": "http error"}
            return HttpResponse(exc.code, payload)
