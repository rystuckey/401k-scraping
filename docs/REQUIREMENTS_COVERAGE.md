# Requirements Coverage

This document maps every requirement from the original brief to the code that satisfies it.

---

## Original requirements

> **Deliverable:** Code base successfully scraping the google search queries and websites for 401k RFPs.

> **Tools:**
> - Use https://docs.crawl4ai.com/ to extract from websites + google search links, trying to get to the RFP PDFs themselves
> - Use https://serper.dev/ for google search queries

> **For each link some sort of metadata should be extracted (maybe even just the page HTML) that could have the LLM identify:**
> - A) size of RFP
> - B) when its due
> - C) link/url
> - D) organization
>
> This can be garbled, but should all be there for the LLM extraction step.

---

## Coverage map

### Serper (Google search)

| Requirement | Status | Implementation |
|---|---|---|
| Use Serper for Google search queries | ✅ Done | `rfp_scraper/serper.py` — `SerperClient.search()` calls `https://google.serper.dev/search` with the configured API key |
| All 38 queries included | ✅ Done | `config/queries.yaml` — `search.queries` list contains all 38 queries as originally specified |
| Results per query configurable | ✅ Done | `--search-results N` CLI flag; default 8 per `config/queries.yaml:search.default_results_per_query` |
| Raw Serper responses saved | ✅ Done | `data/raw/search/*.json` — one file per query, full Serper payload preserved |

### Crawl4AI (web + PDF extraction)

| Requirement | Status | Implementation |
|---|---|---|
| Use Crawl4AI for website extraction | ✅ Done | `rfp_scraper/crawler.py` — `Crawl4AIClient` uses `AsyncWebCrawler` when Crawl4AI is installed |
| Follow links to reach RFP PDFs | ✅ Done | `rfp_scraper/extract.py:pick_pdf_links()` finds `.pdf` links on crawled pages; `pipeline.py:_crawl_discovered_pdfs()` fetches each one |
| Handle direct PDF URLs from search | ✅ Done | `pipeline.py:_process_pdf_hit()` routes direct PDF URLs to `crawler.crawl_pdf()` |
| Fallback when Crawl4AI unavailable | ✅ Done | `crawler.py` — `HAS_CRAWL4AI` flag; fallback uses `requests` + `BeautifulSoup` (HTML) + `pypdf` (PDFs). This allows the pipeline to run on Python 3.14 where Crawl4AI is not yet installable. |
| All 20 source URLs crawled | ✅ Done | `config/queries.yaml:source_urls` — all 20 URLs included; fed directly into the pipeline as seed hits |

### Metadata extraction (LLM handoff fields)

| Requirement | Field(s) captured | How it's captured |
|---|---|---|
| **A) Size of RFP** (assets, participants) | `size_signal_guess` (heuristic pre-fill) + `markdown_path` / `pdf_records[].markdown_path` (full evidence) | Regex pattern `SIZE_PATTERN` in `extract.py` extracts the first numeric/currency amount near "assets", "participants", etc. Full PDF text preserved for LLM verification |
| **B) When it's due** | `due_date_guess` (heuristic pre-fill) + `markdown_path` / `pdf_records[].markdown_path` (full evidence) | Regex pattern `DATE_PATTERN` in `extract.py` extracts the first date following "due", "deadline", "proposals due", etc. |
| **C) Link / URL** | `source_url`, `final_url`, `discovered_pdf_urls`, `pdf_records[].pdf_url` | Preserved from Serper results; updated after redirects; PDF links extracted from pages |
| **D) Organization** | `organization_guess` (heuristic pre-fill) + `page_metadata` + `html_path` / `markdown_path` (full evidence) | `guess_organization()` in `extract.py` tries page `<title>`, OG metadata, then domain; full page text preserved |

### Evidence preservation ("can be garbled, but should all be there")

| Evidence type | Where saved | Purpose |
|---|---|---|
| Raw page HTML | `data/raw/pages/*.html` | Fallback evidence for any parsing errors |
| Page text/markdown | `data/raw/pages/*.md` | Primary LLM input for HTML pages |
| Page metadata | `data/raw/pages/*.metadata.json` | Title, description, OG data |
| Discovered links | `data/raw/pages/*.links.json` | All anchor tags on the page |
| PDF extracted text | `data/raw/pdfs/*.md` | Primary LLM input for PDF documents |
| PDF metadata | `data/raw/pdfs/*.metadata.json` | Embedded author, title, page count |
| PDF binary | `data/raw/pdfs/*.pdf` | Raw document — can be re-parsed or OCR'd |
| Raw Serper response | `data/raw/search/*.json` | Full Google result including snippet, related searches |

All raw evidence is preserved even when heuristics fail. The heuristic fields in `candidates.jsonl` are pre-fills intended as hints, not authoritative extraction.

---

## Query and URL completeness check

### Search queries

The original brief listed 38 queries. All 38 are present in `config/queries.yaml`.

To verify:

```powershell
python -c "
import yaml
d = yaml.safe_load(open('config/queries.yaml'))
print(len(d['search']['queries']), 'queries loaded')
"
```

Expected output: `38 queries loaded`

### Source URLs

The original brief listed 20 source URLs. All 20 are present in `config/queries.yaml`.

To verify:

```powershell
python -c "
import yaml
d = yaml.safe_load(open('config/queries.yaml'))
print(len(d['source_urls']), 'source URLs loaded')
"
```

Expected output: `20 source URLs loaded`

---

## Known limitations and planned mitigations

| Limitation | Affected sites | Mitigation |
|---|---|---|
| Login-walled sites (OpenGov, PlanetBids) | `procurement.opengov.com`, `home.planetbids.com`, `publicpurchase.com` | The Google `site:` queries in Category 8 reach individual RFP pages that are publicly cached even if the portal requires login. Session support can be added to `crawler.py` via Crawl4AI's `SessionManagement` API. |
| JavaScript-rendered content | HigherGov, some SAM.gov pages | Crawl4AI's headless Chromium mode handles this. In fallback mode, the raw HTML is still preserved. |
| Scanned PDFs (image-based) | Older government RFP PDFs | `pypdf` returns blank text. Future enhancement: route blank PDF markdown to an OCR step (`pytesseract` or Claude vision). |
| Rate limiting by target sites | High-traffic scraping targets | The pipeline runs sequentially (one page at a time). `--crawl-limit` provides per-run throttling. Add `time.sleep()` in `pipeline.py:run()` between crawls if rate-limiting becomes an issue. |

---

## File index

| File | Role |
|---|---|
| `main.py` | CLI entry point |
| `rfp_scraper/pipeline.py` | Orchestration: search → dedupe → crawl → output |
| `rfp_scraper/serper.py` | Serper API client |
| `rfp_scraper/crawler.py` | Crawl4AI + fallback crawler |
| `rfp_scraper/extract.py` | Heuristic pre-fill: dates, sizes, org names, PDF links |
| `rfp_scraper/models.py` | Data classes: SearchHit, CandidateRecord |
| `rfp_scraper/storage.py` | File I/O helpers |
| `rfp_scraper/config.py` | YAML config loader |
| `config/queries.yaml` | All 38 queries, 20 URLs, crawl settings |
| `docs/RUNBOOK.md` | Setup and operational guide |
| `docs/DATA_SCHEMA.md` | Field-by-field schema reference |
| `docs/QUERY_STRATEGY.md` | Query rationale and maintenance guide |
| `docs/LLM_HANDOFF.md` | How to feed output to Claude for final extraction |
| `docs/REQUIREMENTS_COVERAGE.md` | This file |
