# Runbook: 401k RFP Scraper

This is the end-to-end operational guide for setup, running, interpreting output, and troubleshooting.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.10+ (3.11 or 3.12 recommended for Crawl4AI; 3.14 uses fallback mode) |
| Serper API key | Sign up free at https://serper.dev — 2,500 free credits on signup |
| Network access | Outbound HTTPS to `google.serper.dev` and all target websites |

---

## Setup

### 1. Clone or place the project

The project lives at `c:\Users\rstuc\projects\farther\401k\`.

### 2. Create the virtual environment (if not already done)

```powershell
cd c:\Users\rstuc\projects\farther\401k
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If using the shared project venv at `c:\Users\rstuc\projects\.venv`:

```powershell
c:/Users/rstuc/projects/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

### 3. Optional: install Crawl4AI and Playwright (Python 3.10–3.13 only)

In this Python 3.14 workspace the code automatically falls back to `requests` + `BeautifulSoup` + `pypdf`. If you want the full Crawl4AI experience (headless browser, JavaScript rendering, login hooks), use a Python 3.11/3.12 venv:

```powershell
pip install crawl4ai
python -m playwright install
```

### 4. Create your `.env` file

Copy the example and fill in your key:

```powershell
copy .env.example .env
```

Edit `.env`:

```
SERPER_API_KEY=your_real_key_here
```

Never commit `.env` — it is in `.gitignore`.

---

## Verifying setup

Preview the loaded configuration without spending API credits:

```powershell
python main.py show-config
```

Expected output: a JSON blob showing 38 queries, 20 source URLs, and crawl settings.

---

## Running the pipeline

### Command format

```powershell
python main.py run [options]
```

All flags are optional. Without flags, the full 38-query × 8-results run plus all 20 source URLs is executed.

### Flags

| Flag | Type | Description |
|---|---|---|
| `--query-limit N` | int | Run only the first N queries from the YAML list |
| `--search-results N` | int | Ask Serper for N results per query (default 8, max 100) |
| `--crawl-limit N` | int | Cap total URLs crawled after deduplication |
| `--skip-search` | flag | Skip Serper entirely; only crawl the 20 configured source URLs |
| `--skip-source-urls` | flag | Skip source URLs; only crawl search result links |
| `--config PATH` | path | Use a different YAML config (default: `config/queries.yaml`) |

### Recommended run profiles

**Proof-of-concept / first test (spends ~10 Serper credits):**
```powershell
python main.py run --query-limit 1 --search-results 3 --crawl-limit 5
```

**Conservative daily run (spends ~80 Serper credits):**
```powershell
python main.py run --query-limit 10 --search-results 8 --crawl-limit 60
```

**Full weekly run (spends ~304 Serper credits – all 38 queries × 8 results):**
```powershell
python main.py run --crawl-limit 200
```

**Source URLs only (0 Serper credits):**
```powershell
python main.py run --skip-search --crawl-limit 20
```

---

## What runs during execution

1. For each search query, Serper returns up to N Google organic results.
2. Each result URL and each configured source URL becomes a candidate hit.
3. Duplicate URLs across all queries are deduplicated.
4. Each URL is crawled:
   - If the URL ends in `.pdf` → PDF extraction path
   - Otherwise → HTML page path, then PDF links on that page are discovered and extracted
5. All raw artifacts are written to `data/raw/`.
6. One normalized record per URL is written to `data/processed/candidates.jsonl` and `candidates.csv`.

---

## Output files

```
data/
├── raw/
│   ├── search/          ← One .json per Serper query response
│   ├── pages/           ← Per crawled page: .html, .md, .metadata.json, .links.json, (optional .network.json)
│   └── pdfs/            ← Per extracted PDF: .md (text), .metadata.json, .pdf (binary)
└── processed/
    ├── candidates.jsonl  ← One JSON record per candidate (newline-delimited)
    └── candidates.csv    ← Spreadsheet-friendly flat version of the same records
```

Full field descriptions are in [DATA_SCHEMA.md](DATA_SCHEMA.md).

---

## Serper credit usage

| Run profile | Queries | Results/query | Credits used |
|---|---|---|---|
| Proof-of-concept | 1 | 3 | 3 |
| Conservative | 10 | 8 | 80 |
| Full | 38 | 8 | 304 |
| Full (10 results) | 38 | 10 | 380 |

Credit costs per query are 1:1 with results on the Starter tier. Monitor your balance at https://serper.dev.

---

## Modifying queries and source URLs

All queries and seed URLs live in `config/queries.yaml`. You can:

- Add/remove queries under `search.queries`
- Add/remove source URLs under `source_urls`
- Change `default_results_per_query` (per-query override, still overridden by `--search-results`)
- Change `crawl.max_pdf_links_per_page` to follow more or fewer PDF links per page

See [QUERY_STRATEGY.md](QUERY_STRATEGY.md) for rationale on the current set.

---

## Troubleshooting

### `SERPER_API_KEY is required`
Your `.env` file is missing or not being picked up. Confirm the file is named exactly `.env` (not `.env.txt`) in the project root, and contains `SERPER_API_KEY=yourkeyhere`.

### `HTTPError 401` from Serper
Your API key is invalid or expired. Generate a new one at https://serper.dev/dashboard.

### `HTTPError 429` from Serper
You have exhausted your Serper credits. Purchase more at https://serper.dev.

### Crawl returns empty markdown / empty HTML
The site returned JavaScript-rendered content that the fallback crawler (requests + BeautifulSoup) cannot see. This is the main limitation of the fallback mode. To resolve:
1. Create a Python 3.11 or 3.12 venv
2. `pip install crawl4ai && python -m playwright install`
3. Re-run the pipeline — it will auto-detect Crawl4AI and use headless Chromium

### Site returns 403 / 401
The site requires a login or blocks scrapers. The record will still write with `error` field populated and `page_status_code: 403`. The raw domain is still preserved for manual review.

### PDF extraction returns blank markdown
The PDF is scanned (image-based). `pypdf` cannot extract text from images. Future enhancement: add an OCR pass with `pytesseract` or an LLM vision call.

### Pipeline runs but `candidates.jsonl` is empty
Check that `--skip-search` and `--skip-source-urls` are not both set at the same time.
