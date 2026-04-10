# Query Strategy: 401k RFP Scraper

This document explains the rationale behind the 38 search queries and 20 source URLs in `config/queries.yaml`, how they are used, and how to maintain or expand them.

---

## How queries are used

Each query in `search.queries` is sent directly to the Serper API as a Google search. Google does full query interpretation including `site:`, `filetype:`, `inurl:`, `OR`, `-exclusions`, and `intitle:` operators.

The results (organic links, titles, snippets) are fed into the crawl pipeline. The code does **not** modify queries before sending — what you type in YAML is what Google receives.

---

## The 38 queries: by category

### Category 1: Procurement platform deep searches (3 queries)
Target the two highest-yield procurement aggregators directly — OpenGov and HigherGov.

```
procurement.opengov.com 457 401 recordkeeping deferred compensation RFP proposals due
procurement.opengov.com retirement plan consulting investment advisory RFP solicitation
procurement.opengov.com 403b third party administration retirement plan RFP
```

**Why:** OpenGov and HigherGov are the densest sources of active government RFPs. Querying them by domain concentrates credits on the highest-signal pages.

---

### Category 2: Geography-broad government DC plan searches (10 queries)
Catch RFPs from any city, county, municipality, or state that didn't appear on a procurement platform.

```
city 457 deferred compensation recordkeeper RFP proposals due 2025 2026
county 457b 401a recordkeeping retirement plan RFP solicitation 2025 2026
municipality retirement plan recordkeeping services RFP deadline 2025 2026
state government 457 deferred compensation plan recordkeeper RFP 2025 2026
public employee retirement defined contribution recordkeeper solicitation RFP 2025 2026
government retirement plan third party administrator RFP proposals due 2025 2026
stable value fund manager search RFP defined contribution pension 2025 2026
target date fund manager search defined contribution plan RFP 2025 2026
investment consultant defined contribution advisory services RFP 2025 2026
police fire public safety retirement plan recordkeeping RFP 2025 2026
```

**Why:** Many smaller municipalities post RFPs only on their own `.gov` site and never appear in a procurement aggregator. Year tokens `2025 2026` bias results toward active/upcoming deadlines.

---

### Category 3: Education and nonprofit (2 queries)
University 403(b) plans and nonprofit foundations are a separate market segment from government 457 plans.

```
university endowment 403b defined contribution recordkeeper RFP proposals 2025 2026
nonprofit foundation 403b retirement plan administrator RFP proposals 2025 2026
```

**Why:** 403(b) plans for universities and nonprofits are a parallel market. They often appear under `.edu` domains and procurement portals that don't overlap with government searches.

---

### Category 4: HigherGov direct platform (2 queries)
```
highergov.com 457 401 recordkeeping retirement plan solicitation 2025 2026
highergov state local government retirement plan recordkeeper RFP 2025 2026
```

**Why:** HigherGov is a Google-indexed procurement database. Searching it by domain surfaces additional listings beyond what appears in the Category 1 OpenGov queries.

---

### Category 5: General procurement vocabulary (2 queries)
```
defined contribution recordkeeping services procurement solicitation deadline 2025 2026
retirement plan services vendor selection RFP government pension 2025 2026
```

**Why:** Catch any pages that didn't use the word "RFP" explicitly but are obviously an active vendor selection process.

---

### Category 6: Advanced `.gov` Google operators (5 queries)
Uses `site:.gov`, `filetype:pdf`, and specific plan-type tokens.

```
site:.gov (RFP OR "request for proposals" OR solicitation) (401k OR "401(k)" OR 403b OR "403(b)" OR 457b OR "457(b)") (recordkeeper OR recordkeeping OR "retirement plan") filetype:pdf (2026 OR "Jan 1 2026" OR "January 1, 2026")
site:.gov (RFP OR "request for proposals") ("governmental 457(b)" OR "457(b)" OR "deferred compensation") (recordkeeping OR recordkeeper OR TPA) filetype:pdf -pension -fire -police
site:.gov filetype:pdf (RFP OR "request for proposals") ("3(38)" OR "ERISA 3(38)" OR "investment manager") (401k OR "401(k)" OR 403b OR "403(b)") -IPS -minutes
site:.gov filetype:(pdf OR doc OR docx) (RFP OR "request for proposals") ("SECURE 2.0" OR "secure 2.0") ("Roth catch-up" OR "Roth catch up" OR "section 603")
site:.gov (inurl:procurement OR inurl:purchasing OR inurl:bids OR inurl:rfp OR inurl:solicitations) (401k OR "401(k)" OR 403b OR "403(b)" OR "retirement plan") (RFP OR "request for proposals") -construction
```

**Why:** `site:.gov filetype:pdf` is the highest-precision combination for finding actual RFP documents (not landing pages). The SECURE 2.0 query specifically targets plans that are rebidding specifically because of the 2022 legislation changes.

---

### Category 7: State top-level domain + municipality (2 queries)
```
site:.us (city OR county OR municipality OR "board of education") (RFP OR "request for proposals") (401k OR "401(k)" OR 403b OR "403(b)" OR 457b OR "457(b)") (recordkeeper OR "retirement services") filetype:pdf
(site:.k12.ca.us OR site:.k12.il.us OR site:.k12.tx.us OR inurl:k12) (RFP OR "request for proposals") (403b OR "403(b)" OR "retirement plan") (recordkeeper OR "plan administration" OR TPA) (filetype:pdf OR filetype:doc OR filetype:docx)
```

**Why:** K-12 school districts are significant 403(b) plan sponsors. Many use `.k12.xx.us` domains and are missed by `.gov` queries.

---

### Category 8: Specific procurement portals by domain (6 queries)
Forces Google to search inside each known procurement portal directly.

```
site:caleprocure.ca.gov ...
site:bidbuy.illinois.gov ...
site:procurement.opengov.com inurl:project-list ...
(site:vendors.planetbids.com OR site:pbsystem.planetbids.com) ...
site:publicpurchase.com ...
(site:demandstar.com OR site:network.demandstar.com) ...
```

**Why:** These portals have their own internal search, but Google often indexes their individual RFP pages. Using `site:` queries reaches RFPs that aren't on the portal's first page in its own search.

---

### Category 9: General filetype PDF with SECURE 2.0 triggers (1 query)
```
("request for proposals" OR RFP) ("401(k)" OR 401k OR "403(b)" OR 403b) ("Roth catch-up" OR "SECURE 2.0" OR "section 603") filetype:pdf -irs -regulations
```

**Why:** SECURE 2.0 Roth catch-up provisions and auto-enrollment mandates require plan sponsors to update their recordkeeper contracts, driving new RFPs. The `-irs -regulations` exclusion removes IRS guidance documents from results.

---

### Category 10: `.edu` institution searches (7 queries)
Universities and colleges are significant 403(b) plan sponsors with their own procurement processes.

```
site:.edu (RFP OR "request for proposals" OR solicitation) (403b OR "403(b)" OR "retirement plan") (recordkeeper OR recordkeeping OR "plan administration" OR TPA) filetype:pdf (2026 OR "SECURE 2.0" OR "Roth catch-up")
site:.edu (inurl:procurement OR inurl:purchasing OR inurl:sourcing OR inurl:bids) (RFP OR "request for proposals") ("retirement plan" OR 401k OR 403b OR recordkeeping)
site:.edu filetype:(doc OR docx OR pdf) (RFP OR "request for proposal") ("investment adviser" OR "investment advisor" OR consultant) ("3(38)" OR "discretionary") (401k OR 403b OR "defined contribution")
site:.edu intitle:(RFP OR "Request for Proposals") ("recordkeeping services" OR recordkeeper OR "retirement services") (401k OR 403b OR "defined contribution")
site:.edu ("request for proposals" OR RFP) ("403(b)" OR 403b) ("custodial" OR "custodial account" OR "annuity provider") filetype:pdf
site:.edu ("SECURE 2.0" OR "Roth catch-up" OR "section 603") ("vendor" OR "recordkeeper" OR "plan administrator") (RFP OR "request for proposals")
```

**Why:** `.edu` sites have their own procurement portals (most commonly Jaggaer, Unimarket, or custom systems). Using `site:.edu` with `inurl:procurement` and `filetype:pdf` catches both documents and procurement portal pages.

---

## The 20 source URLs

These are crawled directly — no Google search needed. They are authoritative procurement listing pages.

| URL | Why it's included |
|---|---|
| https://www.callan.com/rfps/ | Callan Associates is a major investment consultant that publishes active manager search RFPs on its website |
| https://www.nepc.com/advertised-searches/ | NEPC publishes client RFPs for investment manager searches |
| https://www.calpers.ca.gov/search/site?keys=rfp | CalPERS is the largest US public pension; its RFPs are high-value |
| https://www.mass.gov/info-details/retirement-board-request-for-proposal-rfp-notices | Massachusetts PERAC publishes RFP notices for member retirement boards |
| https://www.lacera.com/who-we-are/business-opportunities | LA County Employees Retirement Association business opportunities page |
| https://comptroller.nyc.gov/services/for-businesses/doing-business-with-the-comptroller/rfps-solicitations/ | NYC Comptroller publishes RFPs across all city pension systems |
| https://www.imrf.org/en/about-imrf/procurement/open-rfps | Illinois Municipal Retirement Fund open RFPs |
| https://www.calstrs.com/investment-solicitations | CalSTRS investment solicitations (California teachers pension) |
| https://www.trs.texas.gov/procurement | Texas Teacher Retirement System procurement |
| https://www.sparkinstitute.org/news/ | SPARK Institute news — often includes industry RFP announcements |
| https://www.highergov.com/contract-opportunity/?naics=523130&q=recordkeeping+retirement | HigherGov filtered view of recordkeeping/retirement NAICS 523130 contracts |
| https://www.nasra.org/jobs_search.asp?proc=y | NASRA procurement searches for state retirement systems |
| https://www.highergov.com/sl/contract-opportunity/?searchID=UAI-i2MmiIKWclMLr5aDp | HigherGov state/local DC plan RFPs saved search |
| https://alpha.sam.gov/find-contract-opportunities | SAM.gov federal contract opportunities |
| https://naspovaluepoint.org/solicitation-status/ | NASPO ValuePoint cooperative procurement solicitations |
| https://caleprocure.ca.gov/pages/ | California eProcure homepage for state procurement |
| https://www.bidbuy.illinois.gov/bso/view/search/external/advancedSearchBid.xhtml?openBids=true | Illinois BidBuy open bids |
| https://procurement.opengov.com/login | OpenGov Procurement portal (requires login for full access; landing page still surfaces public links) |
| https://home.planetbids.com/vendor-basic | PlanetBids vendor portal homepage |
| https://www.publicpurchase.com/gems/register/vendor/register | PublicPurchase vendor registration — public bids visible |

---

## How to add or modify queries

1. Open `config/queries.yaml`
2. Add a new line under `search.queries:` following the same YAML list format
3. Run `python main.py show-config` to confirm parsing
4. Test with `--query-limit` pointing to only your new query's position

**Tips for effective queries:**
- Keep year tokens current (`2025 2026`, then update to `2026 2027` in late 2026)
- Always test a new query in Google manually first to see what it returns before adding
- Use `filetype:pdf` when you want direct document links (skips landing pages)
- Use `-construction -facility -maintenance` exclusions to filter procurement noise

---

## Refresh cadence

| Activity | Frequency |
|---|---|
| Full run (all 38 queries + 20 URLs) | Weekly, Monday morning |
| Quick source-URL-only check | Every 2-3 days during active seasons (Q1, Q3) |
| Query review and updates | Quarterly — update year tokens, add emerging query patterns |
| Source URL audit | Quarterly — check each URL is still live and returning relevant results |
