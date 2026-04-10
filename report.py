"""
report.py - Generate a self-contained HTML research report from candidates.jsonl

Usage:
    python report.py                         # top 50 candidates, output to data/processed/report.html
    python report.py --limit 100             # top 100
    python report.py --all                   # all likely_rfp=True records
    python report.py --output my_report.html

Ranks by signal strength:
  +3 has due_date_guess
  +2 has size_signal_guess
  +2 has at least one successful PDF
  +1 likely_rfp=True
  -2 has error
"""

import argparse
import ast
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

CANDIDATES_FILE = Path("data/processed/candidates.jsonl")
DEFAULT_OUTPUT = Path("data/processed/report.html")
MAX_PDF_CHARS = 8000   # chars of PDF text to embed per record (keeps file manageable)
MAX_PAGE_CHARS = 3000  # chars of page text when no PDF available


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_record(rec: dict) -> int:
    s = 0
    if rec.get("likely_rfp"):
        s += 1
    if rec.get("due_date_guess", "").strip():
        s += 3
    if rec.get("size_signal_guess", "").strip():
        s += 2
    if rec.get("error", "").strip():
        s -= 2

    pdf_records = _parse_pdf_records(rec)
    if any(p.get("success") for p in pdf_records):
        s += 2

    return s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pdf_records(rec: dict):
    """Parse pdf_records which may be a list or a JSON string."""
    raw = rec.get("pdf_records", [])
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(raw)
            except Exception:
                pass
    return []


def read_md(path_str: str, max_chars: int) -> str:
    """Read a markdown file, returning up to max_chars characters."""
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.exists():
        return f"[File not found: {path_str}]"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... [truncated — {len(text):,} total chars]"
        return text
    except Exception as e:
        return f"[Could not read file: {e}]"


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return iso or "—"


# ---------------------------------------------------------------------------
# HTML building
# ---------------------------------------------------------------------------

CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; padding: 0; background: #f5f5f5; color: #222; }
.header { background: #1a3a5c; color: white; padding: 24px 32px; }
.header h1 { margin: 0 0 4px; font-size: 1.6em; }
.header p  { margin: 0; opacity: .7; font-size: .9em; }
.container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
.summary-table { width: 100%; border-collapse: collapse; background: white;
                 border-radius: 8px; overflow: hidden;
                 box-shadow: 0 1px 4px rgba(0,0,0,.12); margin-bottom: 32px; }
.summary-table th { background: #1a3a5c; color: white; text-align: left;
                    padding: 10px 12px; font-size: .82em; white-space: nowrap; }
.summary-table td { padding: 8px 12px; border-bottom: 1px solid #eee;
                    font-size: .82em; vertical-align: top; }
.summary-table tr:last-child td { border-bottom: none; }
.summary-table tr:hover td { background: #f0f4ff; }
.summary-table a { color: #1a3a5c; }
.badge { display: inline-block; padding: 2px 7px; border-radius: 10px;
         font-size: .75em; font-weight: 600; }
.badge-green  { background: #d4edda; color: #155724; }
.badge-yellow { background: #fff3cd; color: #856404; }
.badge-red    { background: #f8d7da; color: #721c24; }
.badge-score  { background: #e0e7ff; color: #3730a3; }
.card { background: white; border-radius: 8px; margin-bottom: 24px;
        box-shadow: 0 1px 4px rgba(0,0,0,.12); overflow: hidden; }
.card-header { background: #1a3a5c; color: white; padding: 14px 18px;
               display: flex; justify-content: space-between; align-items: flex-start; }
.card-header h2 { margin: 0; font-size: 1em; flex: 1; margin-right: 12px; }
.card-header .score-badge { background: rgba(255,255,255,.25); padding: 3px 10px;
                             border-radius: 12px; font-size: .8em; white-space: nowrap; }
.card-meta { display: flex; flex-wrap: wrap; gap: 10px; padding: 12px 18px;
             border-bottom: 1px solid #eee; font-size: .82em; }
.card-meta-item { display: flex; flex-direction: column; }
.card-meta-item .label { font-size: .72em; color: #888; text-transform: uppercase;
                          letter-spacing: .04em; margin-bottom: 2px; }
.card-meta-item .value { font-weight: 600; }
.card-meta-item a { color: #1a3a5c; word-break: break-all; }
.section-title { font-size: .75em; text-transform: uppercase; letter-spacing: .06em;
                 color: #888; padding: 12px 18px 4px; }
pre.pdf-text { white-space: pre-wrap; word-break: break-word; font-family: monospace;
               font-size: .78em; line-height: 1.5; background: #f8f9fa;
               margin: 0 18px 18px; padding: 12px; border-radius: 4px;
               max-height: 400px; overflow-y: auto; border: 1px solid #e0e0e0; }
.error-box { background: #fff3f3; border: 1px solid #f5c6cb; border-radius: 4px;
             padding: 10px 14px; margin: 0 18px 18px; font-size: .82em; color: #721c24; }
.toc { background: white; border-radius: 8px; padding: 16px 20px;
       box-shadow: 0 1px 4px rgba(0,0,0,.12); margin-bottom: 28px; }
.toc h3 { margin: 0 0 10px; font-size: .9em; text-transform: uppercase;
           letter-spacing: .06em; color: #888; }
.toc ol { margin: 0; padding-left: 20px; }
.toc li { font-size: .83em; margin-bottom: 4px; }
.toc a  { color: #1a3a5c; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
"""


def signal_badge(rec: dict) -> str:
    has_date = bool(rec.get("due_date_guess", "").strip())
    has_size = bool(rec.get("size_signal_guess", "").strip())
    has_error = bool(rec.get("error", "").strip())
    if has_error:
        return '<span class="badge badge-red">Error</span>'
    if has_date and has_size:
        return '<span class="badge badge-green">Strong</span>'
    if has_date or has_size:
        return '<span class="badge badge-yellow">Partial</span>'
    return '<span class="badge badge-yellow">Weak</span>'


def build_summary_table(records: list) -> str:
    rows = []
    for i, rec in enumerate(records, 1):
        anchor = f"rec-{i}"
        title = html.escape(rec.get("title", "") or rec.get("url", ""))[:90]
        org = html.escape(rec.get("organization_guess", "") or "—")[:50]
        due = html.escape(rec.get("due_date_guess", "") or "—")
        size = html.escape(rec.get("size_signal_guess", "") or "—")[:60]
        url = rec.get("source_url") or rec.get("final_url") or ""
        domain = html.escape(rec.get("domain", "") or "")
        sig = signal_badge(rec)
        sc = score_record(rec)

        rows.append(f"""
        <tr>
          <td><a href="#{anchor}">{i}</a></td>
          <td><a href="#{anchor}">{title}</a></td>
          <td>{org}</td>
          <td>{due}</td>
          <td>{size}</td>
          <td><a href="{html.escape(url)}" target="_blank">{domain}</a></td>
          <td>{sig}</td>
          <td><span class="badge badge-score">{sc}</span></td>
        </tr>""")

    return f"""
    <table class="summary-table">
      <thead><tr>
        <th>#</th><th>Title</th><th>Organization</th>
        <th>Due Date</th><th>Size Signal</th>
        <th>Domain</th><th>Signal</th><th>Score</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def build_toc(records: list) -> str:
    items = []
    for i, rec in enumerate(records, 1):
        title = (rec.get("title") or rec.get("url") or "")[:80]
        items.append(f'<li><a href="#rec-{i}">{i}. {html.escape(title)}</a></li>')
    return f"""
    <div class="toc">
      <h3>Contents ({len(records)} candidates)</h3>
      <ol>{"".join(items)}</ol>
    </div>"""


def build_card(i: int, rec: dict) -> str:
    anchor = f"rec-{i}"
    title = html.escape(rec.get("title", "") or rec.get("url", "") or "Untitled")
    sc = score_record(rec)
    org = html.escape(rec.get("organization_guess", "") or "Unknown")
    due = html.escape(rec.get("due_date_guess", "") or "Not found")
    size = html.escape(rec.get("size_signal_guess", "") or "Not found")
    url = rec.get("source_url") or rec.get("final_url") or ""
    collected = fmt_date(rec.get("collected_at", ""))
    snippet = html.escape(rec.get("snippet", "") or "")
    error = rec.get("error", "").strip()
    query = html.escape(rec.get("source_query", "") or "")

    # PDF text content
    pdf_records = _parse_pdf_records(rec)
    pdf_sections = []
    for j, pr in enumerate(pdf_records, 1):
        if not pr.get("success"):
            continue
        md_path = pr.get("markdown_path", "")
        pdf_url = html.escape(pr.get("pdf_url", ""))
        text = read_md(md_path, MAX_PDF_CHARS)
        pdf_sections.append(f"""
        <div class="section-title">PDF {j}: <a href="{pdf_url}" target="_blank">{pdf_url}</a></div>
        <pre class="pdf-text">{html.escape(text)}</pre>""")

    # Fall back to page markdown if no PDFs
    page_text_section = ""
    if not pdf_sections:
        md_path = rec.get("markdown_path", "")
        if md_path:
            text = read_md(md_path, MAX_PAGE_CHARS)
            page_text_section = f"""
            <div class="section-title">Page Text</div>
            <pre class="pdf-text">{html.escape(text)}</pre>"""

    error_section = ""
    if error:
        error_section = f'<div class="error-box"><strong>Error:</strong> {html.escape(error)}</div>'

    content = "".join(pdf_sections) or page_text_section or ""

    return f"""
    <div class="card" id="{anchor}">
      <div class="card-header">
        <h2>{title}</h2>
        <span class="score-badge">Score: {sc}</span>
      </div>
      <div class="card-meta">
        <div class="card-meta-item">
          <span class="label">Organization</span>
          <span class="value">{org}</span>
        </div>
        <div class="card-meta-item">
          <span class="label">Due Date</span>
          <span class="value">{due}</span>
        </div>
        <div class="card-meta-item">
          <span class="label">Size / AUM Signal</span>
          <span class="value">{size}</span>
        </div>
        <div class="card-meta-item">
          <span class="label">Source</span>
          <span class="value"><a href="{html.escape(url)}" target="_blank">{html.escape(url)[:80]}</a></span>
        </div>
        <div class="card-meta-item">
          <span class="label">Collected</span>
          <span class="value">{collected}</span>
        </div>
        <div class="card-meta-item">
          <span class="label">Search Query</span>
          <span class="value">{query}</span>
        </div>
      </div>
      {f'<div style="padding:8px 18px;font-size:.82em;color:#555;border-bottom:1px solid #eee"><em>{snippet}</em></div>' if snippet else ""}
      {error_section}
      {content}
    </div>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_candidates(path: Path) -> list[dict]:
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
    parser = argparse.ArgumentParser(description="Generate HTML report from candidates.jsonl")
    parser.add_argument("--input", default=str(CANDIDATES_FILE),
                        help=f"Path to candidates.jsonl (default: {CANDIDATES_FILE})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"Output HTML path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max candidates to include, highest-scored first (default: 50)")
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="Include all likely_rfp=True records (ignores --limit)")
    parser.add_argument("--min-score", type=int, default=None,
                        help="Only include records with score >= this value")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {input_path} ...", end=" ", flush=True)
    all_records = load_candidates(input_path)
    print(f"{len(all_records)} records loaded")

    # Filter: only likely_rfp=True
    candidates = [r for r in all_records if r.get("likely_rfp")]
    print(f"Filtered to {len(candidates)} likely_rfp=True records")

    # Score and sort
    candidates.sort(key=score_record, reverse=True)

    # Apply min-score if requested
    if args.min_score is not None:
        candidates = [r for r in candidates if score_record(r) >= args.min_score]
        print(f"After min-score {args.min_score}: {len(candidates)} records")

    # Apply limit
    if not args.include_all:
        candidates = candidates[: args.limit]

    print(f"Generating report for {len(candidates)} candidates ...")

    # Build HTML
    run_date = datetime.utcnow().strftime("%B %d, %Y %H:%M UTC")
    cards = "".join(build_card(i, rec) for i, rec in enumerate(candidates, 1))

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>401k / 457 RFP Research Report — {run_date}</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="header">
    <h1>401k / 457 RFP Research Report</h1>
    <p>Generated {run_date} &nbsp;|&nbsp; {len(candidates)} candidates shown
       (sorted by signal score)</p>
  </div>
  <div class="container">
    <h2 style="font-size:1em;margin-bottom:10px">Summary Table</h2>
    {build_summary_table(candidates)}
    {build_toc(candidates)}
    {cards}
  </div>
</body>
</html>"""

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")

    size_kb = output_path.stat().st_size // 1024
    print(f"\nReport saved: {output_path}  ({size_kb:,} KB)")
    print(f"Open in browser: start {output_path}")


if __name__ == "__main__":
    main()
