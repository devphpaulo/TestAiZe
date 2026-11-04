"""HTTP client for the loopback capture API. The token is a header, never a URL."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class LocalApi:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None, timeout: float = 20) -> tuple[dict, int]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("X-Testaize-Capture", self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return (json.loads(raw) if raw else {}), response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"error": "Falha ao falar com o TestAíZé.", "code": "LOCAL_SERVICE_UNAVAILABLE"}
            if not isinstance(parsed, dict):
                parsed = {"error": "Falha ao falar com o TestAíZé.", "code": "LOCAL_SERVICE_UNAVAILABLE"}
            return parsed, exc.code
        except (urllib.error.URLError, TimeoutError, OSError):
            return {"error": "TestAíZé indisponível. A captura continua local.", "code": "LOCAL_SERVICE_UNAVAILABLE"}, 0

    def get(self, path: str) -> tuple[dict, int]:
        return self.request("GET", path)

    def post(self, path: str, payload: dict) -> tuple[dict, int]:
        return self.request("POST", path, payload)
