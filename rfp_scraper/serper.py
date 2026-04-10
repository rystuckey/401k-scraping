from __future__ import annotations

import os
from typing import Any

import requests

from .models import SearchHit


class SerperClient:
    def __init__(self, api_key: str | None = None, gl: str = "us", hl: str = "en") -> None:
        self.api_key = api_key or os.getenv("SERPER_API_KEY", "")
        self.gl = gl
        self.hl = hl

    def search(self, query: str, num: int = 8) -> tuple[list[SearchHit], dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("SERPER_API_KEY is required to run search queries.")

        response = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "q": query,
                "gl": self.gl,
                "hl": self.hl,
                "num": num,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        hits: list[SearchHit] = []
        for item in payload.get("organic", []):
            hits.append(
                SearchHit(
                    query=query,
                    title=str(item.get("title", "")).strip(),
                    link=str(item.get("link", "")).strip(),
                    snippet=str(item.get("snippet", "")).strip(),
                    position=item.get("position"),
                    source_type="serper",
                    raw=item,
                )
            )
        return hits, payload