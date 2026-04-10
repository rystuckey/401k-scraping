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
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if loaded is None:
        data: dict[str, Any] = {}
    elif isinstance(loaded, dict):
        data = loaded
    else:
        raise ValueError("config root must be a mapping/object")

    search_data = data.get("search") or {}
    crawl_data = data.get("crawl") or {}
    source_urls = data.get("source_urls") or []

    if not isinstance(search_data, dict):
        raise ValueError("search must be a mapping/object")
    if not isinstance(crawl_data, dict):
        raise ValueError("crawl must be a mapping/object")
    if not isinstance(source_urls, list) or any(not isinstance(url, str) for url in source_urls):
        raise ValueError("source_urls must be a list of strings")

    search = SearchConfig(**search_data)
    crawl = CrawlConfig(**crawl_data)

    if search.queries is None:
        search.queries = []
    elif not isinstance(search.queries, list) or any(not isinstance(query, str) for query in search.queries):
        raise ValueError("search.queries must be a list of strings")

    return AppConfig(search=search, crawl=crawl, source_urls=source_urls)