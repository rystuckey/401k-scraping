from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse


DATE_PATTERN = re.compile(
    r"\b(?:due|deadline|proposal(?:s)?\s+due|responses?\s+due|submission\s+deadline)\b.{0,40}?"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE | re.DOTALL,
)

SIZE_PATTERN = re.compile(
    r"\b(?:participants?|assets?|plan\s+assets|employees?|active\s+members|account\s+balances?)\b.{0,30}?"
    r"(?:\$\s?\d[\d,]*(?:\.\d+)?\s?(?:million|billion|m|bn)?|\d[\d,]*)",
    re.IGNORECASE,
)

RFP_PATTERN = re.compile(
    r"\b(rfp|request for proposals?|solicitation|recordkeep(?:er|ing)|deferred compensation|403\(b\)|401\(k\)|401k|457\(b\)|457b|retirement plan)\b",
    re.IGNORECASE,
)

PDF_HINT_PATTERN = re.compile(r"\.pdf(?:$|\?)|download|attachment|document", re.IGNORECASE)


def domain_for(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_pdf_url(url: str) -> bool:
    return ".pdf" in url.lower()


def text_or_empty(value: object) -> str:
    return str(value or "").strip()


def looks_like_rfp(text: str) -> bool:
    return bool(RFP_PATTERN.search(text_or_empty(text)))


def extract_due_date(text: str) -> str:
    match = DATE_PATTERN.search(text_or_empty(text))
    return match.group(1).strip() if match else ""


def extract_size_signal(text: str) -> str:
    match = SIZE_PATTERN.search(text_or_empty(text))
    return match.group(0).strip() if match else ""


def guess_organization(title: str, metadata: dict | None, url: str) -> str:
    title_text = text_or_empty(title)
    metadata = metadata or {}
    candidates = [
        metadata.get("title", ""),
        metadata.get("site_name", ""),
        title_text,
        domain_for(url),
    ]
    for candidate in candidates:
        cleaned = text_or_empty(candidate)
        if cleaned:
            cleaned = re.sub(r"\s*[\-|:]\s*(RFP|Request for Proposals?).*$", "", cleaned, flags=re.IGNORECASE)
            return cleaned[:180]
    return ""


def pick_pdf_links(links: dict[str, list[dict]], limit: int) -> list[str]:
    picked: list[str] = []
    seen: set[str] = set()
    for bucket in ("internal", "external", "urls"):
        for item in links.get(bucket, []):
            href = text_or_empty(item.get("href") or item.get("url"))
            if not href or href in seen:
                continue
            text_blob = " ".join(
                text_or_empty(item.get(key)) for key in ("text", "title", "context", "desc")
            )
            if is_pdf_url(href) or (PDF_HINT_PATTERN.search(href) and looks_like_rfp(text_blob)):
                seen.add(href)
                picked.append(href)
            if len(picked) >= limit:
                return picked
    return picked


def flatten_text_parts(parts: Iterable[str]) -> str:
    return "\n".join(part for part in (text_or_empty(p) for p in parts) if part)


def likely_rfp_from_parts(*parts: str) -> bool:
    return looks_like_rfp(flatten_text_parts(parts))