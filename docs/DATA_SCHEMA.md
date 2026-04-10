# Data Schema: 401k RFP Scraper

This document describes every field written to `data/processed/candidates.jsonl` and `candidates.csv`, plus the structure of raw files in `data/raw/`.

---

## `candidates.jsonl` / `candidates.csv`

Each line in the JSONL file is one self-contained JSON object representing a single crawled URL (either a web page or a PDF). The CSV is a flat projection of the same data.

### Identification and provenance

| Field | Type | Description |
|---|---|---|
| `collected_at` | ISO 8601 UTC string | Timestamp when the record was written. Example: `"2026-04-10T03:49:42.244058+00:00"` |
| `source_type` | string | How this URL was discovered. `"serper"` = Google search result. `"seed_url"` = manually configured source URL. |
| `source_query` | string | The exact search query that produced this hit (Serper hits), or `"seed_url"` (source URLs). |
| `source_url` | string | The URL as first discovered (from Serper result or config). |
| `page_url` | string | Same as `source_url` for now; preserved for future use with URL normalization. |
| `final_url` | string | The URL after any HTTP redirects. May differ from `source_url` if the server redirected. |
| `domain` | string | Lowercase netloc of `source_url`. Example: `"media.governmentnavigator.com"` |

### Display / classification fields

| Field | Type | Description |
|---|---|---|
| `title` | string | Page title. For Serper results: the result title Google showed. For seed URLs: populated from the page's `<title>` tag after crawl. |
| `snippet` | string | For Serper results: the Google snippet text. For seed URLs: `"Configured source URL"`. |
| `likely_rfp` | boolean | `true` if any of title, snippet, or page text matched the RFP keyword pattern (`rfp`, `request for proposals`, `solicitation`, `recordkeeping`, `deferred compensation`, `403(b)`, `401(k)`, `457(b)`, `retirement plan`). Intended as a filter hint, not a guarantee. |

### LLM extraction targets (heuristic pre-fill)

These fields are best-effort guesses computed with regex before the LLM step. They will often be empty or approximate. The downstream LLM should treat them as hints and use the raw files for authoritative extraction.

| Field | Type | Description | LLM target |
|---|---|---|---|
| `organization_guess` | string | Best guess at the issuing organization, pulled from page `<title>`, OG metadata, or domain. Trailing "— RFP" suffixes are stripped. | **D) Organization** |
| `due_date_guess` | string | First date-like match in the text following words like "due", "deadline", "proposals due", "submission deadline". Examples: `"April 16, 2025"`, `"5/29/25"` | **B) Due date** |
| `size_signal_guess` | string | First match for asset/participant/employee counts near a currency or numeric amount. Example: `"Assets ($) $403,913,088"` | **A) RFP size** |
| `source_url` / `final_url` | string | The canonical URL for this opportunity. | **C) Link/URL** |

### Page crawl result

| Field | Type | Description |
|---|---|---|
| `page_status_code` | int or null | HTTP status code returned by the server. `200` = success. `null` = network-level failure. `403` = access denied. |
| `page_metadata` | object | Python dict of metadata extracted from the page. For HTML pages: `title`, `description`, `og:title`, `og:site_name`, `extractor`. For PDFs: `/Title`, `/Author`, `/Creator`, `num_pages`, `extractor`. |
| `error` | string | Empty if the crawl succeeded. Non-empty contains the exception message if the crawl failed. |

### Raw artifact paths

| Field | Description |
|---|---|
| `html_path` | Absolute path to the saved raw HTML file (`data/raw/pages/*.html`). Empty for direct PDF hits. |
| `markdown_path` | Absolute path to the extracted text as markdown (`data/raw/pages/*.md`). Empty for direct PDF hits. |
| `metadata_path` | Absolute path to the page metadata JSON (`data/raw/pages/*.metadata.json`). |
| `links_path` | Absolute path to the discovered links JSON (`data/raw/pages/*.links.json`). |

These files contain the full evidence for LLM extraction. The markdown file is the primary input (cleaned text). The HTML file is the fallback if parsing missed something.

### PDF records

| Field | Type | Description |
|---|---|---|
| `discovered_pdf_urls` | array of strings | PDF URLs found on the crawled page that were extracted. For direct PDF hits, this contains just `[source_url]`. |
| `pdf_records` | array of objects | One entry per PDF that was downloaded and parsed. See sub-schema below. |

#### `pdf_records[]` sub-schema

| Field | Type | Description |
|---|---|---|
| `pdf_url` | string | URL the PDF was fetched from. |
| `status_code` | int or null | HTTP status of the PDF download. |
| `metadata_path` | string | Path to `data/raw/pdfs/*.metadata.json`. Contains author, title, page count, creation date. |
| `markdown_path` | string | Path to `data/raw/pdfs/*.md`. Contains full extracted text page-by-page. This is the primary LLM input for PDFs. |
| `binary_path` | string | Path to `data/raw/pdfs/*.pdf`. Raw binary download. |
| `success` | boolean | Whether the extraction ran without error. |
| `error` | string | Error message if extraction failed, otherwise empty. |

---

## Raw file formats

### `data/raw/search/*.json`

One file per Serper query. Contains the unmodified Serper API response, including:
- `organic`: list of results with `title`, `link`, `snippet`, `position`
- `searchParameters`: the exact query sent
- `knowledgeGraph`, `peopleAlsoAsk`, `relatedSearches` if present

### `data/raw/pages/*.html`

Full HTML of the crawled page. Useful when BeautifulSoup missed content or when JavaScript-rendered content is needed.

### `data/raw/pages/*.md`

Plain text extracted from the page, formatted as markdown (BeautifulSoup `get_text("\n", strip=True)` or Crawl4AI `raw_markdown`). This is the primary evidence file used by the LLM extraction step.

### `data/raw/pages/*.metadata.json`

Page-level metadata: `title`, `description`, `og:title`, `og:site_name`.

### `data/raw/pages/*.links.json`

All links discovered on the page, split into `internal` and `external` buckets. Each link has: `href`, `text`, `title`.

### `data/raw/pdfs/*.md`

Full text of the PDF, one section per page. This is the primary LLM evidence for PDF-sourced records.

### `data/raw/pdfs/*.metadata.json`

PDF metadata from the file header: author, creator, producer, title, creation date, page count.

---

## File naming convention

All raw files use a deterministic name based on the URL:

```
{slug-of-url}-{12-char-sha1-of-url+query}.ext
```

Example:
```
media-governmentnavigator-com-media-bid-17443070-227748166467.md
```

This means running the same URL twice will overwrite the same files (stable naming), which makes incremental re-runs safe.

---

## Notes for LLM extraction

The four fields the original requirements asked for map to the output as follows:

| Requirement | Pre-fill field | Best raw evidence |
|---|---|---|
| A) Size of RFP (assets/participants) | `size_signal_guess` | `pdf_records[].markdown_path`, `markdown_path` |
| B) Due date | `due_date_guess` | `pdf_records[].markdown_path`, `markdown_path` |
| C) Link / URL | `final_url`, `discovered_pdf_urls` | Already structured |
| D) Organization | `organization_guess` | `page_metadata.title`, `markdown_path` |

The heuristic pre-fills are intentionally loose. They will often capture the right value on clean PDFs, but may be wrong or empty on complex pages. Always give the LLM the raw markdown text to verify or override what the heuristics found.
