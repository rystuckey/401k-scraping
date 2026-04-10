from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.async_configs import BrowserConfig
    from crawl4ai.processors.pdf import PDFContentScrapingStrategy, PDFCrawlerStrategy

    HAS_CRAWL4AI = True
except Exception:
    AsyncWebCrawler = None
    CrawlerRunConfig = None
    BrowserConfig = None
    PDFContentScrapingStrategy = None
    PDFCrawlerStrategy = None
    HAS_CRAWL4AI = False


class Crawl4AIClient:
    def __init__(
        self,
        downloads_dir: str | Path,
        capture_network_requests: bool = True,
        capture_console_messages: bool = False,
        accept_downloads: bool = True,
    ) -> None:
        self.downloads_dir = Path(downloads_dir)
        self.capture_network_requests = capture_network_requests
        self.capture_console_messages = capture_console_messages
        self.accept_downloads = accept_downloads
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    async def crawl_page(self, url: str) -> dict[str, Any]:
        if not HAS_CRAWL4AI:
            return self._crawl_page_fallback(url)

        browser_config = BrowserConfig(
            headless=True,
            accept_downloads=self.accept_downloads,
            downloads_path=str(self.downloads_dir),
        )
        run_config = CrawlerRunConfig(
            capture_network_requests=self.capture_network_requests,
            capture_console_messages=self.capture_console_messages,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            markdown = getattr(result, "markdown", None)
            raw_markdown = ""
            if markdown:
                raw_markdown = getattr(markdown, "raw_markdown", "") or str(markdown)

            return {
                "url": result.url,
                "success": result.success,
                "status_code": getattr(result, "status_code", None),
                "html": getattr(result, "html", "") or "",
                "cleaned_html": getattr(result, "cleaned_html", "") or "",
                "markdown": raw_markdown,
                "metadata": getattr(result, "metadata", None) or {},
                "links": getattr(result, "links", None) or {},
                "downloaded_files": getattr(result, "downloaded_files", None) or [],
                "network_requests": getattr(result, "network_requests", None) or [],
                "console_messages": getattr(result, "console_messages", None) or [],
                "error_message": getattr(result, "error_message", "") or "",
            }

    async def crawl_pdf(self, url: str) -> dict[str, Any]:
        if not HAS_CRAWL4AI:
            return self._crawl_pdf_fallback(url)

        run_config = CrawlerRunConfig(scraping_strategy=PDFContentScrapingStrategy())

        async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            markdown = getattr(result, "markdown", None)
            raw_markdown = ""
            if markdown:
                raw_markdown = getattr(markdown, "raw_markdown", "") or str(markdown)

            return {
                "url": result.url,
                "success": result.success,
                "status_code": getattr(result, "status_code", None),
                "markdown": raw_markdown,
                "metadata": getattr(result, "metadata", None) or {},
                "links": getattr(result, "links", None) or {},
                "media": getattr(result, "media", None) or {},
                "pdf_bytes": getattr(result, "pdf", None),
                "error_message": getattr(result, "error_message", "") or "",
            }

    def _crawl_page_fallback(self, url: str) -> dict[str, Any]:
        response = requests.get(
            url,
            headers={"User-Agent": self.user_agent},
            timeout=60,
        )
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        base_domain = urlparse(url).netloc.lower()

        metadata = {
            "title": soup.title.get_text(strip=True) if soup.title else "",
            "description": self._meta_content(soup, "description"),
            "og:title": self._meta_property(soup, "og:title"),
            "og:site_name": self._meta_property(soup, "og:site_name"),
            "extractor": "fallback",
        }

        links: dict[str, list[dict[str, str]]] = {"internal": [], "external": []}
        for anchor in soup.select("a[href]"):
            href = urljoin(url, anchor.get("href", "").strip())
            if not href.startswith(("http://", "https://")):
                continue
            bucket = "internal" if urlparse(href).netloc.lower() == base_domain else "external"
            links[bucket].append(
                {
                    "href": href,
                    "text": anchor.get_text(" ", strip=True),
                    "title": anchor.get("title", "") or "",
                    "context": "",
                }
            )

        markdown = soup.get_text("\n", strip=True)
        return {
            "url": response.url,
            "success": response.ok,
            "status_code": response.status_code,
            "html": html,
            "cleaned_html": html,
            "markdown": markdown,
            "metadata": metadata,
            "links": links,
            "downloaded_files": [],
            "network_requests": [],
            "console_messages": [],
            "error_message": "",
        }

    def _crawl_pdf_fallback(self, url: str) -> dict[str, Any]:
        response = requests.get(
            url,
            headers={"User-Agent": self.user_agent},
            timeout=90,
        )
        response.raise_for_status()

        reader = PdfReader(io.BytesIO(response.content))
        extracted_pages: list[str] = []
        for page in reader.pages:
            try:
                extracted_pages.append(page.extract_text() or "")
            except Exception:
                extracted_pages.append("")

        metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
        metadata["num_pages"] = len(reader.pages)
        metadata["extractor"] = "fallback"

        return {
            "url": response.url,
            "success": response.ok,
            "status_code": response.status_code,
            "markdown": "\n\n".join(extracted_pages),
            "metadata": metadata,
            "links": {},
            "media": {},
            "pdf_bytes": response.content,
            "error_message": "",
        }

    def _meta_content(self, soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else ""

    def _meta_property(self, soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("meta", attrs={"property": name})
        return tag.get("content", "").strip() if tag else ""