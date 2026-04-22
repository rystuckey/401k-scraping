"""Post-processing filters to exclude old RFPs and closed solicitations."""

from __future__ import annotations

from datetime import datetime

from .extract_enhanced import (
    detect_rfp_status,
    flatten_text_parts,
    is_date_valid_and_future,
    score_rfp_recency,
)
from .models import CandidateRecord


UNWANTED_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
)


def _is_unwanted_domain(domain: str) -> bool:
    lowered = (domain or "").lower()
    return any(lowered == bad or lowered.endswith(f".{bad}") for bad in UNWANTED_DOMAINS)


def filter_unwanted_domains(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Remove social/media domains that are usually irrelevant to open RFP discovery."""
    return [r for r in records if not _is_unwanted_domain(r.domain)]


def filter_non_rfps(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Keep only records that pass the stricter likely_rfp heuristic."""
    return [r for r in records if r.likely_rfp]


def filter_closed_rfps(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Remove RFPs that are marked as 'closed' or have explicitly ended."""
    return [r for r in records if r.rfp_status != "closed"]


def filter_past_deadlines(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Remove RFPs with deadlines that have already passed."""
    return [r for r in records if r.due_date_valid or not r.due_date_guess]


def filter_by_deadline_window(
    records: list[CandidateRecord],
    min_days: int = 0,
    max_days: int = 180,
) -> list[CandidateRecord]:
    """
    Filter RFPs by deadline window.
    
    Args:
        min_days: Minimum days until due (default: 0 = include overdue)
        max_days: Maximum days until due (default: 180 = ~6 months)
    
    Only keeps RFPs with valid future dates within this window.
    """
    filtered: list[CandidateRecord] = []
    today = datetime.now()
    for record in records:
        if not record.due_date_guess:
            # Keep records with no date (may be actively open)
            filtered.append(record)
            continue

        is_valid, parsed = is_date_valid_and_future(record.due_date_guess, today=today)
        if not is_valid or parsed is None:
            continue

        days_until_due = (parsed - today).days
        if min_days <= days_until_due <= max_days:
            filtered.append(record)
    
    return filtered


def rank_by_deadline_urgency(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Sort RFPs by how soon they're due (soonest first)."""
    def sort_key(record: CandidateRecord) -> tuple:
        # Sort by: status (open first), then recency score (highest first)
        status_priority = (0 if record.rfp_status == "open" else 1)
        return (status_priority, -record.recency_score)
    
    return sorted(records, key=sort_key)


def enrich_candidate_with_status(
    record: CandidateRecord,
    page_text: str | None = None,
    snippet_text: str | None = None,
) -> CandidateRecord:
    """
    Enrich a candidate record with status detection and date validation.
    
    Updates:
    - rfp_status: 'open', 'closed', or 'unknown'
    - due_date_valid: True if date is in future
    - recency_score: 0.0-1.0 based on deadline urgency
    """
    # Detect RFP status from available text
    text_to_analyze = flatten_text_parts([page_text or "", snippet_text or record.snippet, record.title])
    record.rfp_status = detect_rfp_status(text_to_analyze)
    
    # Validate due date
    if record.due_date_guess:
        is_valid, _ = is_date_valid_and_future(record.due_date_guess)
        record.due_date_valid = is_valid
        record.recency_score = score_rfp_recency(record.due_date_guess)
    
    return record


def apply_filtering_pipeline(
    records: list[CandidateRecord],
    exclude_unwanted_domains: bool = True,
    require_likely_rfp: bool = True,
    exclude_closed: bool = True,
    exclude_past_deadlines: bool = True,
    sort_by_urgency: bool = True,
) -> list[CandidateRecord]:
    """
    Apply all filtering steps in sequence.
    
    Args:
        records: List of candidate records
        exclude_closed: Remove records with 'closed' status
        exclude_past_deadlines: Remove records with invalid or past dates
        sort_by_urgency: Sort by deadline urgency (soonest first)
    
    Returns:
        Filtered and optionally sorted list of records
    """
    result = records

    if exclude_unwanted_domains:
        result = filter_unwanted_domains(result)

    if require_likely_rfp:
        result = filter_non_rfps(result)
    
    if exclude_closed:
        result = filter_closed_rfps(result)
    
    if exclude_past_deadlines:
        result = filter_past_deadlines(result)
    
    if sort_by_urgency:
        result = rank_by_deadline_urgency(result)
    
    return result
