# 401k RFP Scraper

Automated discovery and capture pipeline for 401k, 403(b), and 457 RFPs.
Only **currently active, submittable** RFPs are kept — closed, expired, and social-media noise is filtered out automatically.

## How it works

1. **Search** — runs 46 optimized Google queries through Serper (monthly recency filter)
2. **Crawl** — fetches each result page and extracts content; follows PDF links to the actual RFP documents
3. **Preserve** — saves raw HTML, page text, PDF text, and metadata for each URL
4. **Filter** — removes social domains, non-RFP results, closed solicitations, and past deadlines automatically
5. **Pre-fill** — extracts organization, due date (future-validated), size, recency score, and open/closed status
6. **LLM handoff** — structured output ready for Claude to perform final extraction

## Documentation

| Doc | Purpose |
|---|---|
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Setup, environment, all run commands, troubleshooting |
| [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md) | Every field in `candidates.jsonl`, raw file descriptions |
| [docs/QUERY_STRATEGY.md](docs/QUERY_STRATEGY.md) | Why each query and source URL exists; how to maintain them |
| [docs/LLM_HANDOFF.md](docs/LLM_HANDOFF.md) | How to feed pipeline output to Claude; example extraction script |
| [docs/REQUIREMENTS_COVERAGE.md](docs/REQUIREMENTS_COVERAGE.md) | Maps every original requirement to the implementing code |

## Quick start

> **Important:** Always use `run.ps1` — do NOT use plain `python.exe`, which resolves to the Windows Store stub and is missing project dependencies.

```powershell
# 1. Navigate to project folder
cd C:\Users\rstuc\projects\farther\401k

# 2. Allow scripts for this terminal session (once per session)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# 3. Create .env with your API key (first time only)
#    Contents of .env:
#    SERPER_API_KEY=your_key_here
#    ANTHROPIC_API_KEY=your_key_here  (optional, for LLM extraction)

# 4. Verify config loads correctly
.\run.ps1 show-config

# 5. Small test run (~15 Serper credits, proven working)
.\run.ps1 run --query-limit 3 --search-results 5 --crawl-limit 15

# 6. Conservative run (~80 Serper credits)
.\run.ps1 run --query-limit 10 --search-results 8 --crawl-limit 60

# 7. Full weekly run (~460 Serper credits, all 46 queries)
.\run.ps1 run --crawl-limit 200

# 8. Pure search-only run (no seed URLs, max signal)
.\run.ps1 run --query-limit 46 --search-results 10 --crawl-limit 250 --skip-source-urls
```

Outputs: `data/processed/candidates.jsonl` and `data/processed/candidates.csv`

## Check output after a run

```powershell
# How many records survived filtering?
Get-Content data/processed/candidates.jsonl | Measure-Object -Line

# Quick quality audit
Get-Content data/processed/candidates.jsonl | ForEach-Object {
    $o = $_ | ConvertFrom-Json
    "$($o.domain) | $($o.likely_rfp) | $($o.due_date_guess) | $($o.rfp_status) | $($o.recency_score)"
} | Select-Object -First 20

# Domain distribution
Get-Content data/processed/candidates.jsonl | ForEach-Object {
    ($_ | ConvertFrom-Json).domain
} | Group-Object | Sort-Object Count -Descending | Select-Object -First 15
```

## LLM extraction (optional next step)

After a scraper run, feed the output to Claude:

```powershell
# Requires ANTHROPIC_API_KEY in .env
.\run.ps1 run  # ensure candidates.jsonl is fresh first
C:\Users\rstuc\projects\farther\401k\.venv\Scripts\python.exe extract_with_llm.py
```

Produces `data/processed/extracted.jsonl` with structured fields: organization, due_date, size, url, confidence. See [docs/LLM_HANDOFF.md](docs/LLM_HANDOFF.md) for full details.