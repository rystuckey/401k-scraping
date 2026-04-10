# 401k RFP Scraper

Automated discovery and capture pipeline for 401k, 403(b), and 457 RFPs.

## How it works

1. **Search** — runs 38 Google queries through Serper to find RFP pages and PDFs
2. **Crawl** — fetches each result page and extracts content; follows PDF links to the actual RFP documents
3. **Preserve** — saves raw HTML, page text, PDF text, and metadata for each URL
4. **Pre-fill** — extracts best-effort guesses for organization, due date, size, and URL
5. **LLM handoff** — structured output ready for Claude to perform final extraction

## Documentation

| Doc | Purpose |
|---|---|
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Setup, environment, all run commands, troubleshooting |
| [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md) | Every field in `candidates.jsonl`, raw file descriptions |
| [docs/QUERY_STRATEGY.md](docs/QUERY_STRATEGY.md) | Why each of the 38 queries and 20 source URLs exists; how to maintain them |
| [docs/LLM_HANDOFF.md](docs/LLM_HANDOFF.md) | How to feed pipeline output to Claude; example extraction script |
| [docs/REQUIREMENTS_COVERAGE.md](docs/REQUIREMENTS_COVERAGE.md) | Maps every original requirement to the implementing code |

## Quick start

```powershell
# 1. Install dependencies
c:/Users/rstuc/projects/.venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. Create .env with SERPER_API_KEY=your_key_here

# 3. Verify config loads
c:/Users/rstuc/projects/.venv/Scripts/python.exe main.py show-config

# 4. Small test run (3 Serper credits)
c:/Users/rstuc/projects/.venv/Scripts/python.exe main.py run --query-limit 1 --search-results 3 --crawl-limit 5

# 5. Conservative daily run (~80 Serper credits)
c:/Users/rstuc/projects/.venv/Scripts/python.exe main.py run --query-limit 10 --search-results 8 --crawl-limit 60

# 6. Full weekly run (~304 Serper credits, all 38 queries)
c:/Users/rstuc/projects/.venv/Scripts/python.exe main.py run --crawl-limit 200
```

Outputs: `data/processed/candidates.jsonl` and `candidates.csv`

## LLM extraction (optional next step)

After a scraper run, feed the output to Claude:

```powershell
# Requires ANTHROPIC_API_KEY in .env
c:/Users/rstuc/projects/.venv/Scripts/python.exe extract_with_llm.py
```

Produces `data/processed/extracted.jsonl` with structured fields: organization, due_date, size, url, confidence. See [docs/LLM_HANDOFF.md](docs/LLM_HANDOFF.md) for full details.