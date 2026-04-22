"""Enhanced extraction with RFP status detection and date validation."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import urlparse


# Stricter date extraction - only accepts clear deadlines
DATE_PATTERN = re.compile(
    r"\b(?:due|deadline|proposals?\s+due|responses?\s+due|submission\s+deadline|closes?|open\s+until|deadline\s+for)\b.{0,60}?"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE | re.DOTALL,
)

# Open/active status keywords
OPEN_STATUS_KEYWORDS = re.compile(
    r"\b(open\s+until|currently\s+accepting|accepting\s+proposals|now\s+open|open\s+for|open\s+bids|bid\s+opportunity|solicitation|RFP\s+issued|questions\s+due|intent\s+to\s+bid|active\s+solicitation)\b",
    re.IGNORECASE
)

# Closed/expired keywords
CLOSED_STATUS_KEYWORDS = re.compile(
    r"\b(closed|awarded|selected|deadline\s+passed|expired|past\s+deadline|no\s+longer\s+accepting|cancelled|cancelled|archived)\b",
    re.IGNORECASE
)

# Strong RFP markers - only count if present
STRONG_RFP_MARKERS = re.compile(
    r"\b(request\s+for\s+proposals?|RFP|solicitation|proposal\s+request|sealed\s+bids?|bid\s+specifications?)\b",
    re.IGNORECASE
)

# Related keywords that confirm RFP context
RETIREMENT_CONTEXT = re.compile(
    r"\b(401\(k\)|401k|403\(b\)|403b|457\(b\)|457b|deferred\s+compensation|ERISA|retirement\s+plan|defined\s+contribution|recordkeep(?:er|ing)|third\s+party\s+admin|TPA|custodian|recordkeeping\s+services)\b",
    re.IGNORECASE
)

SIZE_PATTERN = re.compile(
    r"\b(?:participants?|assets?|plan\s+assets|employees?|active\s+members|account\s+balances?)\b.{0,30}?"
    r"(?:\$\s?\d[\d,]*(?:\.\d+)?\s?(?:million|billion|m|bn)?|\d[\d,]*)",
    re.IGNORECASE,
)

PDF_HINT_PATTERN = re.compile(r"\.pdf(?:$|\?)|download|attachment|document", re.IGNORECASE)


def domain_for(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_pdf_url(url: str) -> bool:
    return ".pdf" in url.lower()


def text_or_empty(value: object) -> str:
    return str(value or "").strip()


def parse_due_date(date_str: str) -> datetime | None:
    """Parse extracted date string to datetime, with validation."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try various date formats
    formats = [
        "%B %d, %Y",    # January 15, 2026
        "%b %d, %Y",    # Jan 15, 2026
        "%m/%d/%Y",     # 01/15/2026
        "%m/%d/%y",     # 01/15/26
        "%B %d %Y",     # January 15 2026
        "%b %d %Y",     # Jan 15 2026
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def is_date_valid_and_future(due_date_str: str, today: datetime | None = None) -> tuple[bool, datetime | None]:
    """
    Check if extracted date is valid AND in the future (giving 90-day window).
    Returns (is_valid, parsed_datetime).
    """
    if not due_date_str:
        return False, None
    
    parsed = parse_due_date(due_date_str)
    if not parsed:
        return False, None
    
    if today is None:
        today = datetime.now()
    
    # Only accept dates that are:
    # 1. In the future (hasn't passed yet)
    # 2. Within 180 days (not too far in future - likely real deadline)
    min_date = today
    max_date = today + timedelta(days=180)
    
    if min_date <= parsed <= max_date:
        return True, parsed
    
    return False, None


def extract_due_date_strict(text: str) -> str:
    """Extract due date with validation."""
    match = DATE_PATTERN.search(text_or_empty(text))
    if match:
        date_str = match.group(1).strip()
        is_valid, _ = is_date_valid_and_future(date_str)
        if is_valid:
            return date_str
    return ""


def detect_rfp_status(text: str) -> str:
    """
    Detect if RFP is open, closed, or unknown.
    Returns: 'open', 'closed', or 'unknown'
    """
    text_lower = text_or_empty(text).lower()
    
    if CLOSED_STATUS_KEYWORDS.search(text_lower):
        return "closed"
    
    if OPEN_STATUS_KEYWORDS.search(text_lower):
        return "open"
    
    return "unknown"


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
            # Remove RFP-specific suffixes
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


def looks_like_rfp(text: str) -> bool:
    """
    STRICTER check: must have strong RFP marker AND retirement context.
    Prevents capturing budgets, articles, meeting notes, etc.
    """
    text_lower = text_or_empty(text).lower()
    
    # Must have explicit RFP/solicitation language
    if not STRONG_RFP_MARKERS.search(text_lower):
        return False
    
    # Must have retirement plan context
    if not RETIREMENT_CONTEXT.search(text_lower):
        return False
    
    return True


def likely_rfp_from_parts(*parts: str) -> bool:
    """Use stricter RFP detection."""
    return looks_like_rfp(flatten_text_parts(parts))


def score_rfp_recency(due_date_str: str) -> float:
    """
    Score RFP by recency: 1.0 = due very soon, 0.5 = due in 3 months, 0.0 = too far out.
    Used for ranking results.
    """
    is_valid, parsed = is_date_valid_and_future(due_date_str)
    if not is_valid or not parsed:
        return 0.0
    
    today = datetime.now()
    days_until_due = (parsed - today).days
    
    if days_until_due <= 7:
        return 1.0  # Due this week - HIGH PRIORITY
    elif days_until_due <= 30:
        return 0.9  # Due this month
    elif days_until_due <= 60:
        return 0.7  # Due in 2 months
    elif days_until_due <= 90:
        return 0.5  # Due in 3 months
    else:
        return 0.2  # Beyond 3 months
