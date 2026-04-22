from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SearchHit:
    query: str
    title: str
    link: str
    snippet: str = ""
    position: int | None = None
    source_type: str = "serper"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateRecord:
    collected_at: str
    source_type: str
    source_query: str
    source_url: str
    page_url: str
    final_url: str
    domain: str
    title: str
    snippet: str
    likely_rfp: bool
    organization_guess: str
    due_date_guess: str
    size_signal_guess: str
    page_status_code: int | None
    page_metadata: dict[str, Any]
    discovered_pdf_urls: list[str]
    html_path: str
    markdown_path: str
    metadata_path: str
    links_path: str
    pdf_records: list[dict[str, Any]]
    rfp_status: str = "unknown"  # 'open', 'closed', or 'unknown'
    due_date_valid: bool = False  # True if due_date is in future and valid
    recency_score: float = 0.0  # 0.0-1.0, higher = sooner deadline
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)