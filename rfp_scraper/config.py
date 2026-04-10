from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class SearchConfig:
    gl: str = "us"
    hl: str = "en"
    default_results_per_query: int = 8
    queries: list[str] | None = None


@dataclass(slots=True)
class CrawlConfig:
    max_follow_links_per_page: int = 10
    max_pdf_links_per_page: int = 4
    capture_network_requests: bool = True
    capture_console_messages: bool = False
    accept_downloads: bool = True


@dataclass(slots=True)
class AppConfig:
    search: SearchConfig
    crawl: CrawlConfig
    source_urls: list[str]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    search = SearchConfig(**(data.get("search") or {}))
    crawl = CrawlConfig(**(data.get("crawl") or {}))
    source_urls = data.get("source_urls") or []

    if search.queries is None:
        search.queries = []

    return AppConfig(search=search, crawl=crawl, source_urls=source_urls)