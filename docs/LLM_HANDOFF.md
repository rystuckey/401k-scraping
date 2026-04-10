# LLM Handoff Guide: 401k RFP Scraper

This document describes how to take the pipeline output and pass it to Claude (or any other LLM) to perform the final structured extraction of the four required fields:

- **A) Size of RFP** (plan assets, participants, or AUM)
- **B) Due date** (proposal submission deadline)
- **C) Link / URL** (the canonical URL for the RFP document or listing)
- **D) Organization** (the issuing entity — city, county, university, fund, etc.)

---

## Where the raw evidence lives

After a pipeline run, each candidate record in `candidates.jsonl` contains file paths to the raw evidence. The LLM should receive the text content of these files, not just the heuristic pre-fill fields.

| Evidence source | Field(s) to read | Best for |
|---|---|---|
| Page markdown | `markdown_path` | HTML procurement pages (HigherGov, OpenGov, municipal sites) |
| Page HTML | `html_path` | Fallback if markdown is garbled |
| Page metadata | `page_metadata` | Title, site name — good for organization |
| PDF markdown | `pdf_records[].markdown_path` | RFP PDF documents — highest signal for all four fields |
| PDF metadata | `pdf_records[].metadata_path` | Embedded title, author, creation date |
| Snippet | `snippet` | Quick filter — from Google search result |

For any record, the priority order for the LLM evidence input is:
1. `pdf_records[].markdown_path` (if PDFs were found) — most complete
2. `markdown_path` (page text) — second best
3. `snippet` + `title` + `page_metadata` — minimum viable context

---

## Example: single-record Claude extraction call

Below is a Python script pattern you can run per-record or in batch. The `candidates.jsonl` file is the input.

```python
import json
from pathlib import Path

import anthropic  # pip install anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

EXTRACTION_PROMPT = """
You are reviewing a potential retirement plan RFP (Request for Proposals) document.
Extract the following four fields from the text below. If a field is not present, return null.

Fields to extract:
- organization: The name of the entity issuing the RFP (city, county, university, pension fund, etc.)
- due_date: The deadline for submitting proposals. Return in ISO 8601 format (YYYY-MM-DD) if possible. Return the raw text if you cannot parse a date.
- size: Any indication of plan size — total assets under management, number of participants, account balances, or AUM. Include the unit (e.g., "$403,913,088 in assets", "1,200 participants").
- url: The most direct URL to the RFP document or listing.

Also return:
- confidence: high / medium / low — your confidence that this is a genuine active 401k/403b/457 recordkeeping or investment advisory RFP deadline.
- notes: One sentence explaining what this RFP is about, if determinable.

Return a JSON object with keys: organization, due_date, size, url, confidence, notes.
Do not include any other text.

---
{evidence}
"""


def build_evidence(record: dict) -> str:
    parts = []

    # Always include title and snippet
    if record.get("title"):
        parts.append(f"TITLE: {record['title']}")
    if record.get("snippet"):
        parts.append(f"SNIPPET: {record['snippet']}")
    if record.get("source_url"):
        parts.append(f"SOURCE URL: {record['source_url']}")
    if record.get("final_url") and record["final_url"] != record.get("source_url"):
        parts.append(f"FINAL URL: {record['final_url']}")

    # Heuristic pre-fills (hints for the LLM, not authoritative)
    if record.get("organization_guess"):
        parts.append(f"ORGANIZATION HINT: {record['organization_guess']}")
    if record.get("due_date_guess"):
        parts.append(f"DUE DATE HINT: {record['due_date_guess']}")
    if record.get("size_signal_guess"):
        parts.append(f"SIZE HINT: {record['size_signal_guess']}")

    # PDF text (best evidence — include first 12,000 chars)
    for pdf in record.get("pdf_records", []):
        pdf_md = Path(pdf.get("markdown_path", ""))
        if pdf_md.exists():
            text = pdf_md.read_text(encoding="utf-8")[:12000]
            parts.append(f"\n--- PDF TEXT ({pdf['pdf_url']}) ---\n{text}")
            break  # First PDF is usually the main RFP document

    # Page markdown (second best — include first 6,000 chars)
    if not any("PDF TEXT" in p for p in parts):
        page_md = Path(record.get("markdown_path", ""))
        if page_md.exists():
            text = page_md.read_text(encoding="utf-8")[:6000]
            parts.append(f"\n--- PAGE TEXT ---\n{text}")

    return "\n".join(parts)


def extract_record(record: dict) -> dict:
    evidence = build_evidence(record)
    message = client.messages.create(
        model="claude-opus-4-5",
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

    # Merge the extracted fields back with original record identifiers
    return {
        "source_url": record.get("source_url"),
        "collected_at": record.get("collected_at"),
        "source_query": record.get("source_query"),
        **extracted,
    }


def run_extraction(jsonl_path: str, output_path: str, limit: int | None = None) -> None:
    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if limit:
        records = records[:limit]

    # Optional: filter to only likely_rfp=True before spending LLM tokens
    records = [r for r in records if r.get("likely_rfp")]

    results = []
    for i, record in enumerate(records, 1):
        print(f"Extracting {i}/{len(records)}: {record.get('source_url', '')[:80]}")
        result = extract_record(record)
        results.append(result)

    with open(output_path, "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(results)} extracted records to {output_path}")


if __name__ == "__main__":
    run_extraction(
        jsonl_path="data/processed/candidates.jsonl",
        output_path="data/processed/extracted.jsonl",
    )
```

Save this as `extract_with_llm.py` in the project root. Run with:

```powershell
python extract_with_llm.py
```

Set `ANTHROPIC_API_KEY` in your `.env` file before running:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Batch / cost management

Each extraction call sends approximately 1,000–15,000 tokens depending on PDF length.

| Model | Input cost (est.) | Output cost (est.) | Cost per 100 records |
|---|---|---|---|
| claude-opus-4-5 | $15/M tokens | $75/M tokens | ~$0.15–1.50 |
| claude-sonnet-4-5 | $3/M tokens | $15/M tokens | ~$0.04–0.35 |
| claude-haiku-3 | $0.25/M tokens | $1.25/M tokens | ~$0.004–0.04 |

Recommendation: use `claude-haiku-3` for a first pass to filter likely_rfp candidates, then `claude-sonnet-4-5` for records with high-value PDFs.

To skip records the scraper already flagged as not likely RFPs:
```python
records = [r for r in records if r.get("likely_rfp")]
```

---

## Prompt tuning

The extraction prompt above can be modified for different goals:

- **Add more fields:** Add `plan_type: (401k / 403b / 457 / other)` and `service_type: (recordkeeping / advisory / TPA / target-date / stable-value)` to the field list.
- **Add context about your firm:** Prepend a sentence like "We are a defined contribution recordkeeper. Focus on RFPs relevant to recordkeeping services." to bias relevance judgments.
- **Change the confidence scale:** Add criteria like "high = active RFP with clear deadline in 2025–2027, medium = likely RFP but deadline unclear, low = may be a closed or historical solicitation."

---

## Output format from the LLM step

Each row in `extracted.jsonl` will look like:

```json
{
  "source_url": "https://media.governmentnavigator.com/media/bid/1744307014_2025-04-10_2025-RFP-0013.pdf",
  "collected_at": "2026-04-10T06:01:19.490748+00:00",
  "source_query": "procurement.opengov.com 457 401 recordkeeping deferred compensation RFP proposals due",
  "organization": "City of Somecity, Department of Finance",
  "due_date": "2025-05-15",
  "size": "$403,913,088 in plan assets",
  "url": "https://media.governmentnavigator.com/media/bid/1744307014_2025-04-10_2025-RFP-0013.pdf",
  "confidence": "high",
  "notes": "457(b) deferred compensation and 401(a) defined contribution plan recordkeeping RFP with April 16 submission deadline."
}
```

This is the final output ready for review, CRM entry, or business development tracking.
