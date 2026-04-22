"""
prepare_for_claude.py - Build a clean text file for pasting/uploading to Claude.ai

Produces a single .txt file where each candidate is a structured block with:
  - key metadata (org, due date, size signal, URL, query)
  - the first N chars of extracted PDF text (so Claude sees actual RFP content)

Usage:
    python prepare_for_claude.py                  # top 40 by score -> claude_input.txt
    python prepare_for_claude.py --limit 60
    python prepare_for_claude.py --min-score 3    # only high-confidence leads
    python prepare_for_claude.py --all            # all 183 likely_rfp=True (may be large)
    python prepare_for_claude.py --no-pdf-text    # metadata only, no PDF content

Tokens rule of thumb: 1 token ≈ 4 chars. Claude.ai limit ≈ 200K tokens (~800K chars).
Default settings produce ~60-80K tokens, comfortably within limit.
"""


import argparse
from datetime import datetime
import ast
import json
import sys
from pathlib import Path

CANDIDATES_FILE = Path("data/processed/candidates.jsonl")
OUTPUT_FILE = Path("data/processed/claude_input.txt")

PDF_TEXT_CHARS = 2500   # chars of PDF text per record (≈625 tokens)
PAGE_TEXT_CHARS = 1000  # chars of page text when no PDF


# ── scoring (same as report.py) ──────────────────────────────────────────────

def score(rec: dict) -> int:
    s = 0
    if rec.get("likely_rfp"):       s += 1
    if rec.get("due_date_guess", "").strip():  s += 3
    if rec.get("size_signal_guess", "").strip(): s += 2
    if rec.get("error", "").strip():  s -= 2
    if any(p.get("success") for p in _pdfs(rec)):  s += 2
    return s


def _pdfs(rec: dict) -> list:
    raw = rec.get("pdf_records", [])
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            try:
                return ast.literal_eval(raw)
            except Exception:
                pass
    return []


# ── text helpers ─────────────────────────────────────────────────────────────

def read_text(path_str: str, max_chars: int) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n[... truncated, {len(text):,} chars total]"
        return text
    except Exception:
        return ""


def best_text(rec: dict, pdf_chars: int, page_chars: int) -> str:
    """Return the best available text: first successful PDF, else page markdown."""
    for pr in _pdfs(rec):
        if pr.get("success"):
            t = read_text(pr.get("markdown_path", ""), pdf_chars)
            if t:
                return t, pr.get("pdf_url", "")
    # no PDF — try page markdown
    t = read_text(rec.get("markdown_path", ""), page_chars)
    return t, rec.get("final_url", "")


# ── formatting ────────────────────────────────────────────────────────────────

DIVIDER = "=" * 70

def format_record(i: int, rec: dict, include_pdf: bool) -> str:
    lines = [
        DIVIDER,
        f"CANDIDATE #{i}  (score: {score(rec)})",
        DIVIDER,
        f"Title:        {rec.get('title', '').strip() or '—'}",
        f"Organization: {rec.get('organization_guess', '').strip() or '—'}",
        f"Due Date:     {rec.get('due_date_guess', '').strip() or 'NOT FOUND'}",
        f"Size Signal:  {rec.get('size_signal_guess', '').strip() or 'NOT FOUND'}",
        f"Source URL:   {rec.get('source_url') or rec.get('final_url') or '—'}",
        f"Domain:       {rec.get('domain', '').strip() or '—'}",
        f"Search Query: {rec.get('source_query', '').strip() or '—'}",
        f"Error:        {rec.get('error', '').strip() or 'none'}",
        f"Snippet:      {rec.get('snippet', '').strip() or '—'}",
    ]

    if include_pdf:
        text, text_url = best_text(rec, PDF_TEXT_CHARS, PAGE_TEXT_CHARS)
        if text:
            lines.append(f"\n--- Extracted Text ({text_url}) ---")
            lines.append(text)
        else:
            lines.append("\n--- Extracted Text: none available ---")

    lines.append("")  # blank line after each record
    return "\n".join(lines)


SYSTEM_PROMPT = """\
TASK
====
You are a research assistant helping identify active 401k/457(b) recordkeeping
RFPs (Requests for Proposals) that a retirement plan services firm should respond to.

Today's date is {date}.

Below is a list of {n} candidate documents discovered by a web scraper targeting
government, university, and public-sector procurement portals.

For each candidate, please:
1. Determine if it is a GENUINE RFP for retirement plan recordkeeping or
   administration services (not cloud IT, not a response template, not board minutes).
2. If genuine, extract:
   - Organization name
   - Plan type (401k / 457(b) / 403(b) / other)
   - Submission deadline (if still open as of {date} — mark CLOSED if past)
   - Estimated plan size (AUM or participant count)
   - Key contact or submission instructions if visible
3. Produce a ranked shortlist of the top open/upcoming opportunities.

Flag anything that looks like a false positive (e.g., cloud RFP response, law review
article, board meeting agenda, closed procurement from 2022).

Candidates follow:
"""


# ── main ─────────────────────────────────────────────────────────────────────

def load(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Prepare candidates.jsonl for upload to Claude.ai browser"
    )
    parser.add_argument("--input", default=str(CANDIDATES_FILE))
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    parser.add_argument("--limit", type=int, default=40,
                        help="Max candidates to include, best-scored first (default: 40)")
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="Include all likely_rfp=True records")
    parser.add_argument("--min-score", type=int, default=None,
                        help="Only include records with score >= N")
    parser.add_argument("--no-pdf-text", dest="no_pdf", action="store_true",
                        help="Omit embedded PDF text (metadata only, much smaller)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    all_records = load(input_path)
    candidates = [r for r in all_records if r.get("likely_rfp")]
    candidates.sort(key=score, reverse=True)

    if args.min_score is not None:
        candidates = [r for r in candidates if score(r) >= args.min_score]

    if not args.include_all:
        candidates = candidates[: args.limit]

    include_pdf = not args.no_pdf

    # Build output
    header = SYSTEM_PROMPT.format(n=len(candidates), date=datetime.now().strftime("%B %d, %Y"))
    blocks = [format_record(i, rec, include_pdf) for i, rec in enumerate(candidates, 1)]
    body = header + "\n\n" + "\n".join(blocks)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")

    size_kb = output_path.stat().st_size // 1024
    approx_tokens = output_path.stat().st_size // 4  # rough: 1 token ≈ 4 bytes

    print(f"Candidates included: {len(candidates)}")
    print(f"PDF text embedded:   {'yes' if include_pdf else 'no'}")
    print(f"Output:              {output_path}")
    print(f"File size:           {size_kb:,} KB")
    print(f"Approx tokens:       ~{approx_tokens:,}  (Claude.ai limit: ~200,000)")
    print()
    if approx_tokens > 180_000:
        print("WARNING: File may be near Claude.ai's context limit.")
        print("         Try: python prepare_for_claude.py --no-pdf-text  (metadata only)")
        print("         Or:  python prepare_for_claude.py --min-score 4")
    else:
        print(f"OK to upload. Open claude.ai, start a new conversation,")
        print(f"click the paperclip/attachment icon, and upload:")
        print(f"  {output_path.resolve()}")


if __name__ == "__main__":
    main()
