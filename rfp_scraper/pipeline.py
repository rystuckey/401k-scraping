from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import AppConfig
from .crawler import Crawl4AIClient
from .extract import (
    domain_for,
    extract_due_date,
    extract_size_signal,
    guess_organization,
    is_pdf_url,
    likely_rfp_from_parts,
    pick_pdf_links,
)
from .models import CandidateRecord, SearchHit, utc_now_iso
from .serper import SerperClient
from .storage import ensure_dir, stable_name, write_bytes, write_csv, write_json, write_jsonl, write_text


class RFPPipeline:
    def __init__(self, config: AppConfig, root_dir: str | Path) -> None:
        self.config = config
        self.root_dir = Path(root_dir)
        self.search_dir = ensure_dir(self.root_dir / "data" / "raw" / "search")
        self.pages_dir = ensure_dir(self.root_dir / "data" / "raw" / "pages")
        self.pdfs_dir = ensure_dir(self.root_dir / "data" / "raw" / "pdfs")
        self.processed_dir = ensure_dir(self.root_dir / "data" / "processed")
        self.serper = SerperClient(gl=config.search.gl, hl=config.search.hl)
        self.crawler = Crawl4AIClient(
            downloads_dir=self.pages_dir / "downloads",
            capture_network_requests=config.crawl.capture_network_requests,
            capture_console_messages=config.crawl.capture_console_messages,
            accept_downloads=config.crawl.accept_downloads,
        )

    async def run(
        self,
        query_limit: int | None = None,
        search_results: int | None = None,
        crawl_limit: int | None = None,
        skip_search: bool = False,
        skip_source_urls: bool = False,
    ) -> list[dict[str, Any]]:
        search_hits: list[SearchHit] = []

        if not skip_search:
            queries = self.config.search.queries[: query_limit or len(self.config.search.queries)]
            per_query = search_results or self.config.search.default_results_per_query
            for index, query in enumerate(queries, start=1):
                hits, payload = self.serper.search(query, num=per_query)
                name = stable_name(f"query-{index}", query)
                write_json(self.search_dir / f"{name}.json", payload)
                search_hits.extend(hits)

        if not skip_source_urls:
            for url in self.config.source_urls:
                search_hits.append(
                    SearchHit(
                        query="seed_url",
                        title=url,
                        link=url,
                        snippet="Configured source URL",
                        source_type="seed_url",
                    )
                )

        deduped_hits = self._dedupe_hits(search_hits)
        if crawl_limit is not None:
            deduped_hits = deduped_hits[:crawl_limit]

        records: list[dict[str, Any]] = []
        for hit in deduped_hits:
            record = await self._process_hit(hit)
            records.append(record.to_dict())

        write_jsonl(self.processed_dir / "candidates.jsonl", records)
        write_csv(self.processed_dir / "candidates.csv", [self._flatten_record(row) for row in records])
        return records

    def _dedupe_hits(self, hits: list[SearchHit]) -> list[SearchHit]:
        seen: set[str] = set()
        deduped: list[SearchHit] = []
        for hit in hits:
            if not hit.link or hit.link in seen:
                continue
            seen.add(hit.link)
            deduped.append(hit)
        return deduped

    async def _process_hit(self, hit: SearchHit) -> CandidateRecord:
        if is_pdf_url(hit.link):
            return await self._process_pdf_hit(hit)
        return await self._process_page_hit(hit)

    async def _process_page_hit(self, hit: SearchHit) -> CandidateRecord:
        collected_at = utc_now_iso()
        base_name = stable_name(hit.link, hit.query or hit.source_type)

        try:
            page = await self.crawler.crawl_page(hit.link)
            markdown_path = write_text(self.pages_dir / f"{base_name}.md", page.get("markdown", ""))
            html_path = write_text(self.pages_dir / f"{base_name}.html", page.get("html", ""))
            metadata_path = write_json(self.pages_dir / f"{base_name}.metadata.json", page.get("metadata", {}))
            links_path = write_json(self.pages_dir / f"{base_name}.links.json", page.get("links", {}))
            if page.get("network_requests"):
                write_json(self.pages_dir / f"{base_name}.network.json", page["network_requests"])

            combined_text = "\n".join([
                hit.title,
                hit.snippet,
                page.get("markdown", ""),
                str(page.get("metadata", {})),
            ])
            discovered_pdf_urls = pick_pdf_links(
                page.get("links", {}),
                limit=self.config.crawl.max_pdf_links_per_page,
            )
            pdf_records = await self._crawl_discovered_pdfs(base_name, discovered_pdf_urls)

            return CandidateRecord(
                collected_at=collected_at,
                source_type=hit.source_type,
                source_query=hit.query,
                source_url=hit.link,
                page_url=hit.link,
                final_url=page.get("url", hit.link),
                domain=domain_for(hit.link),
                title=hit.title or page.get("metadata", {}).get("title", ""),
                snippet=hit.snippet,
                likely_rfp=likely_rfp_from_parts(hit.title, hit.snippet, combined_text),
                organization_guess=guess_organization(hit.title, page.get("metadata"), hit.link),
                due_date_guess=extract_due_date(combined_text),
                size_signal_guess=extract_size_signal(combined_text),
                page_status_code=page.get("status_code"),
                page_metadata=page.get("metadata", {}),
                discovered_pdf_urls=discovered_pdf_urls,
                html_path=str(html_path),
                markdown_path=str(markdown_path),
                metadata_path=str(metadata_path),
                links_path=str(links_path),
                pdf_records=pdf_records,
                error=page.get("error_message", ""),
            )
        except Exception as exc:
            empty_path = self.pages_dir / f"{base_name}.error.txt"
            write_text(empty_path, str(exc))
            return CandidateRecord(
                collected_at=collected_at,
                source_type=hit.source_type,
                source_query=hit.query,
                source_url=hit.link,
                page_url=hit.link,
                final_url=hit.link,
                domain=domain_for(hit.link),
                title=hit.title,
                snippet=hit.snippet,
                likely_rfp=likely_rfp_from_parts(hit.title, hit.snippet),
                organization_guess=guess_organization(hit.title, None, hit.link),
                due_date_guess="",
                size_signal_guess="",
                page_status_code=None,
                page_metadata={},
                discovered_pdf_urls=[],
                html_path="",
                markdown_path="",
                metadata_path="",
                links_path="",
                pdf_records=[],
                error=str(exc),
            )

    async def _process_pdf_hit(self, hit: SearchHit) -> CandidateRecord:
        collected_at = utc_now_iso()
        base_name = stable_name(hit.link, hit.query or hit.source_type)

        try:
            pdf_result = await self.crawler.crawl_pdf(hit.link)
            pdf_records = [self._persist_pdf_result(base_name, hit.link, pdf_result)]
            combined_text = "\n".join(
                [hit.title, hit.snippet, pdf_result.get("markdown", ""), str(pdf_result.get("metadata", {}))]
            )

            return CandidateRecord(
                collected_at=collected_at,
                source_type=hit.source_type,
                source_query=hit.query,
                source_url=hit.link,
                page_url=hit.link,
                final_url=pdf_result.get("url", hit.link),
                domain=domain_for(hit.link),
                title=hit.title,
                snippet=hit.snippet,
                likely_rfp=likely_rfp_from_parts(hit.title, hit.snippet, combined_text),
                organization_guess=guess_organization(hit.title, pdf_result.get("metadata"), hit.link),
                due_date_guess=extract_due_date(combined_text),
                size_signal_guess=extract_size_signal(combined_text),
                page_status_code=pdf_result.get("status_code"),
                page_metadata=pdf_result.get("metadata", {}),
                discovered_pdf_urls=[hit.link],
                html_path="",
                markdown_path="",
                metadata_path="",
                links_path="",
                pdf_records=pdf_records,
                error=pdf_result.get("error_message", ""),
            )
        except Exception as exc:
            return CandidateRecord(
                collected_at=collected_at,
                source_type=hit.source_type,
                source_query=hit.query,
                source_url=hit.link,
                page_url=hit.link,
                final_url=hit.link,
                domain=domain_for(hit.link),
                title=hit.title,
                snippet=hit.snippet,
                likely_rfp=likely_rfp_from_parts(hit.title, hit.snippet),
                organization_guess=guess_organization(hit.title, None, hit.link),
                due_date_guess="",
                size_signal_guess="",
                page_status_code=None,
                page_metadata={},
                discovered_pdf_urls=[hit.link],
                html_path="",
                markdown_path="",
                metadata_path="",
                links_path="",
                pdf_records=[],
                error=str(exc),
            )

    async def _crawl_discovered_pdfs(self, base_name: str, pdf_urls: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, pdf_url in enumerate(pdf_urls, start=1):
            try:
                result = await self.crawler.crawl_pdf(pdf_url)
                records.append(self._persist_pdf_result(f"{base_name}-pdf-{index}", pdf_url, result))
            except Exception as exc:
                records.append(
                    {
                        "pdf_url": pdf_url,
                        "status_code": None,
                        "metadata_path": "",
                        "markdown_path": "",
                        "binary_path": "",
                        "success": False,
                        "error": str(exc),
                    }
                )
        return records

    def _persist_pdf_result(self, base_name: str, pdf_url: str, result: dict[str, Any]) -> dict[str, Any]:
        metadata_path = write_json(self.pdfs_dir / f"{base_name}.metadata.json", result.get("metadata", {}))
        markdown_path = write_text(self.pdfs_dir / f"{base_name}.md", result.get("markdown", ""))
        binary_path = ""
        pdf_bytes = result.get("pdf_bytes")
        if isinstance(pdf_bytes, (bytes, bytearray)):
            binary_path = str(write_bytes(self.pdfs_dir / f"{base_name}.pdf", bytes(pdf_bytes)))

        return {
            "pdf_url": pdf_url,
            "status_code": result.get("status_code"),
            "metadata_path": str(metadata_path),
            "markdown_path": str(markdown_path),
            "binary_path": binary_path,
            "success": bool(result.get("success")),
            "error": result.get("error_message", ""),
        }

    def _flatten_record(self, record: dict[str, Any]) -> dict[str, Any]:
        flat = record.copy()
        flat["page_metadata"] = str(record.get("page_metadata", {}))
        flat["discovered_pdf_urls"] = " | ".join(record.get("discovered_pdf_urls", []))
        flat["pdf_records"] = str(record.get("pdf_records", []))
        return flat


def run_pipeline_sync(pipeline: RFPPipeline, **kwargs: Any) -> list[dict[str, Any]]:
    return asyncio.run(pipeline.run(**kwargs))