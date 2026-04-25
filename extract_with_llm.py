"""
extract_with_llm.py

Takes the scraper output (data/processed/candidates.jsonl) and runs each candidate
through Claude to extract structured fields:
  - organization
  - due_date
  - size (assets / participants)
  - url (canonical RFP link)
  - confidence (high / medium / low)
  - notes (one-line summary)

Output: data/processed/extracted.jsonl

Setup:
    pip install anthropic
    Set ANTHROPIC_API_KEY in .env

Usage:
    python extract_with_llm.py
    python extract_with_llm.py --limit 10
    python extract_with_llm.py --model claude-haiku-3-5 --limit 20
    python extract_with_llm.py --input data/processed/candidates.jsonl --output data/processed/extracted.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


EXTRACTION_PROMPT = """\
You are reviewing a potential retirement plan RFP (Request for Proposals) document.
Extract the following four fields from the text below. If a field is not present, return null.

Fields to extract:
- organization: The name of the entity issuing the RFP (city, county, university, pension fund, etc.)
- due_date: The deadline for submitting proposals. Return in ISO 8601 format (YYYY-MM-DD) if possible. \
Return the raw text string if you cannot parse a date.
- size: Any indication of plan size — total assets under management, number of participants, account \
balances, or AUM. Include the unit (e.g., "$403,913,088 in assets", "1,200 participants").
- url: The most direct URL to the RFP document or listing.

Also return:
- confidence: "high" if this is clearly an active 401k/403b/457 recordkeeping or investment advisory \
RFP with a deadline in 2025-2027. "medium" if likely an RFP but deadline is unclear. \
"low" if this may be closed, historical, or unrelated to DC plan services.
- notes: One sentence explaining what this RFP is for (plan type, service sought, issuing entity).

Return a JSON object with exactly these keys: organization, due_date, size, url, confidence, notes.
Do not include any other text, explanation, or markdown formatting.

---
{evidence}
"""


def build_evidence(record: dict) -> str:
    parts: list[str] = []

    if record.get("title"):
        parts.append(f"TITLE: {record['title']}")
    if record.get("snippet"):
        parts.append(f"SNIPPET: {record['snippet']}")
    if record.get("source_url"):
        parts.append(f"SOURCE URL: {record['source_url']}")
    if record.get("final_url") and record["final_url"] != record.get("source_url"):
        parts.append(f"FINAL URL (after redirect): {record['final_url']}")

    # Heuristic hints — the LLM can use or override these
    if record.get("organization_guess"):
        parts.append(f"ORGANIZATION HINT: {record['organization_guess']}")
    if record.get("due_date_guess"):
        parts.append(f"DUE DATE HINT: {record['due_date_guess']}")
    if record.get("size_signal_guess"):
        parts.append(f"SIZE HINT: {record['size_signal_guess']}")

    # PDF text is the highest-quality evidence — include first 12,000 chars of first PDF
    for pdf in record.get("pdf_records", []):
        pdf_md = Path(pdf.get("markdown_path", ""))
        if pdf_md.exists():
            text = pdf_md.read_text(encoding="utf-8")[:12_000].strip()
            if text:
                parts.append(f"\n--- RFP PDF TEXT ({pdf['pdf_url']}) ---\n{text}")
                break

    # Page markdown is second best — include first 6,000 chars
    if not any("RFP PDF TEXT" in p for p in parts):
        page_md = Path(record.get("markdown_path", ""))
        if page_md.exists():
            text = page_md.read_text(encoding="utf-8")[:6_000].strip()
            if text:
                parts.append(f"\n--- PAGE TEXT ---\n{text}")

    # Page metadata as fallback
    meta = record.get("page_metadata") or {}
    extra = {k: v for k, v in meta.items() if k in ("title", "description", "og:title", "og:site_name") and v}
    if extra:
        parts.append(f"\nPAGE METADATA: {json.dumps(extra)}")

    return "\n".join(parts)


def extract_record(client: Any, record: dict, model: str) -> dict:
    evidence = build_evidence(record)
    message = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(evidence=evidence),
            }
        ],
    )
    raw = message.content[0].text.strip()
    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        extracted = {"raw_response": raw, "parse_error": True}

    return {
        "source_url": record.get("source_url"),
        "final_url": record.get("final_url"),
        "collected_at": record.get("collected_at"),
        "source_query": record.get("source_query"),
        "source_type": record.get("source_type"),
        "input_title": record.get("title"),
        **extracted,
    }


def run(
    input_path: str,
    output_path: str,
    model: str,
    limit: int | None,
    only_likely_rfp: bool,
) -> None:
    llm_enabled = os.getenv("ENABLE_ANTHROPIC_LLM", "0").strip().lower() in {"1", "true", "yes", "y"}
    if not llm_enabled:
        print(
            "LLM extraction is disabled by default. Set ENABLE_ANTHROPIC_LLM=1 to enable this script."
        )
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    records: list[dict] = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if only_likely_rfp:
        before = len(records)
        records = [r for r in records if r.get("likely_rfp")]
        print(f"Filtered to likely_rfp=True: {before} -> {len(records)} records")

    if limit:
        records = records[:limit]

    print(f"Extracting {len(records)} records using {model}...")

    results: list[dict] = []
    for i, record in enumerate(records, 1):
        url = record.get("source_url", "")[:80]
        print(f"  [{i}/{len(records)}] {url}")
        try:
            result = extract_record(client, record, model)
        except Exception as exc:
            result = {
                "source_url": record.get("source_url"),
                "collected_at": record.get("collected_at"),
                "error": str(exc),
            }
        results.append(result)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    high = sum(1 for r in results if r.get("confidence") == "high")
    medium = sum(1 for r in results if r.get("confidence") == "medium")
    low = sum(1 for r in results if r.get("confidence") == "low")
    errors = sum(1 for r in results if r.get("error") or r.get("parse_error"))

    print(f"\nDone. Wrote {len(results)} records to {output_path}")
    print(f"  High confidence: {high}  Medium: {medium}  Low: {low}  Errors: {errors}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract structured RFP fields using Claude.")
    parser.add_argument(
        "--input",
        default="data/processed/candidates.jsonl",
        help="Path to scraper output JSONL (default: data/processed/candidates.jsonl)",
    )
    parser.add_argument(
        "--output",
        default="data/processed/extracted.jsonl",
        help="Path for extracted output JSONL (default: data/processed/extracted.jsonl)",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Claude model to use (default: claude-sonnet-4-5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to extract (default: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_non_rfp",
        help="Include records where likely_rfp=False (default: skip them)",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    run(
        input_path=args.input,
        output_path=args.output,
        model=args.model,
        limit=args.limit,
        only_likely_rfp=not args.include_non_rfp,
    )
