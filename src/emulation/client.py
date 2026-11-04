"""Small transport client; no emulator or viewer dependencies."""

import json
from typing import Any
from urllib.request import Request, urlopen


class RuntimeClient:
    def __init__(self, url: str = "http://127.0.0.1:8765") -> None:
        self.url = url.rstrip("/")

    def snapshot(self) -> dict[str, Any]:
        with urlopen(self.url + "/v1/snapshot", timeout=3) as response:
            return json.load(response)

    def send(self, action: str, data: dict[str, Any]) -> None:
        request = Request(self.url + "/v1/" + action, json.dumps(data).encode(),
                          {"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=3) as response:
            response.read()
