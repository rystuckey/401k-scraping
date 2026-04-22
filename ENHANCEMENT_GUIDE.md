# RFP Scraper Enhancement Guide - Active RFPs Only

## Problem Statement
Your scraper was capturing **many old RFPs** (2020, 2021, 2022, 2023, 2024) mixed with current ones because:
1. ❌ No date validation—past deadlines weren't filtered out
2. ❌ Weak "likely_rfp" logic captured non-RFPs (budgets, articles, meeting notes)
3. ❌ Queries didn't emphasize "currently open/accepting"
4. ❌ No status detection for closed vs. open RFPs

**Example from your data:** Mixed records with due dates ranging from "March 11, 2026" (good) to "May 20, 2020" (6 years old!)

---

## Solution: Three-Layer Filtering System

### **Layer 1: Enhanced Search Queries** ✅
**Location:** `config/queries.yaml`

**Changes Made:**
- ✅ Changed `recency_tbs: qdr:y` → `qdr:m` (last **month** instead of year)
- ✅ Increased `default_results_per_query: 8` → `10`
- ✅ Added 8 new aggressive queries focusing on:
  - `"RFP issued" OR "RFP released"` + `"accepting"`
  - `"currently accepting"` OR `"now accepting"`
  - `"open until"` patterns
  - `"questions due"` OR `"intent to bid"` (indicators of open RFPs)
  - `"bid opportunity"` keywords
  - Monthly references (Feb/Mar/Apr/May 2026)

**Total Queries:** 46 (was 38) - **all optimized for active RFPs**

---

### **Layer 2: Strict Extraction Logic** ✅
**New File:** `rfp_scraper/extract_enhanced.py`

**Key Functions:**

#### Date Validation
```python
is_date_valid_and_future(due_date_str) → (bool, datetime)
```
- Extracts dates from text
- **Validates date is in future** (not past deadline)
- **Enforces 180-day window** (not too far in future)
- Returns validation status + parsed datetime

#### RFP Status Detection
```python
detect_rfp_status(text) → 'open' | 'closed' | 'unknown'
```
- Looks for explicit keywords:
  - **OPEN indicators:** "open until", "currently accepting", "bid opportunity", "open bids", "questions due"
  - **CLOSED indicators:** "closed", "awarded", "deadline passed", "expired", "cancelled"

#### Stricter RFP Detection
```python
looks_like_rfp(text) → bool
```
- **MUST have** explicit RFP/solicitation language (not just keyword presence)
- **MUST have** retirement plan context (401k, 403b, 457b, recordkeeping, etc.)
- Prevents capturing budgets, articles, meeting agendas

#### Recency Scoring
```python
score_rfp_recency(due_date_str) → 0.0-1.0
```
- **1.0:** Due this week (HIGH PRIORITY)
- **0.9:** Due this month
- **0.7:** Due in 2 months
- **0.5:** Due in 3 months
- **0.2:** Beyond 3 months

---

### **Layer 3: Post-Processing Filtering** ✅
**New File:** `rfp_scraper/filters.py`

**Pipeline Functions:**

```python
apply_filtering_pipeline(records, exclude_closed=True, exclude_past_deadlines=True, sort_by_urgency=True)
```

This applies in sequence:
1. **Remove closed RFPs** - filters out `rfp_status == 'closed'`
2. **Remove past deadlines** - keeps only `due_date_valid == True` OR no date extracted
3. **Sort by urgency** - soonest deadlines first

**Before (old output):** Mixed 2020-2026 RFPs, no ordering
**After (new output):** Only active RFPs, sorted by deadline urgency

---

## Updated CandidateRecord Fields

**Three new fields added to track RFP status:**

```python
@dataclass
class CandidateRecord:
    # ... existing fields ...
    rfp_status: str = "unknown"      # 'open', 'closed', or 'unknown'
    due_date_valid: bool = False      # True if due_date is in future
    recency_score: float = 0.0        # 0.0-1.0, higher = sooner deadline
```

---

## How It Works (End-to-End Flow)

### **Search Phase**
```
Google Search (46 optimized queries)
    ↓
Serper API (monthly recency filter + active keywords)
    ↓
Deduplicate URLs
    ↓
Crawl pages & PDFs
```

### **Extraction Phase**
```
Extract text from pages/PDFs
    ↓
Apply STRICT RFP detection
    ↓
Extract due dates (with FUTURE validation)
    ↓
Detect RFP status (open/closed keywords)
    ↓
Score recency urgency (0.0-1.0)
```

### **Filtering Phase** ⭐ KEY IMPROVEMENT
```
All candidate records
    ↓
[Filter] Remove closed RFPs
    ↓
[Filter] Remove past deadlines
    ↓
[Sort] By deadline urgency
    ↓
Output JSONL/CSV (only active, submittable RFPs)
```

---

## Implementation Checklist

### ✅ Already Done
- [x] Created `extract_enhanced.py` with strict date validation + RFP status detection
- [x] Created `filters.py` with filtering pipeline
- [x] Updated `models.py` to add `rfp_status`, `due_date_valid`, `recency_score` fields
- [x] Updated `pipeline.py` imports to use `extract_enhanced`
- [x] Updated `pipeline.py` to apply filtering before output
- [x] Updated `config/queries.yaml` with 46 optimized queries + monthly recency filter

### ⏳ Next Steps (Optional But Recommended)

#### Step 1: Test the enhanced pipeline
```bash
cd c:\Users\rstuc\projects\farther\401k
python -m rfp_scraper.main run --query-limit 5 --search-results 5
```
This will:
- Run first 5 queries
- Get 5 results per query
- Apply filtering automatically
- Output only active RFPs

#### Step 2: Verify syntax
```bash
python -m py_compile rfp_scraper/extract_enhanced.py rfp_scraper/filters.py
```

#### Step 3: Check output quality
After running, examine `data/processed/candidates.jsonl`:
- Should see only RFPs with future deadlines
- Should see `rfp_status: 'open'` or `'unknown'` (no `'closed'`)
- Should be sorted by `recency_score` (highest first = soonest due)

#### Step 4: (Optional) Keep old extract.py as fallback
If you want to compare results or have issues, keep the old `extract.py` module. The new pipeline uses `extract_enhanced.py` exclusively.

---

## Configuration Parameters You Can Adjust

### In `config/queries.yaml`:

**Search Recency** (line 4):
```yaml
recency_tbs: qdr:m  # qdr:m = last month (aggressive)
                    # qdr:y = last year (less aggressive)
                    # qdr:w = last week (very aggressive)
```

**Results Per Query** (line 5):
```yaml
default_results_per_query: 10  # Increase for more results, decrease for speed
```

### In `pipeline.py`, modify the filtering call (around line 78):

```python
# Current: strict filtering
filtered_records = apply_filtering_pipeline(
    records,
    exclude_closed=True,          # Set to False to keep closed RFPs
    exclude_past_deadlines=True,  # Set to False to keep past RFPs
    sort_by_urgency=True,         # Set to False to skip sorting
)
```

---

## What's Different From Your Old Pipeline

| Aspect | Old | New |
|--------|-----|-----|
| **Date Extraction** | Extracts any date from text | Validates date is FUTURE + within 180 days |
| **Date Filtering** | None (all dates kept) | Removes past deadlines automatically |
| **RFP Detection** | Keyword search only | Keyword search + retirement context requirement |
| **Closed RFP Handling** | All RFPs output | Closed RFPs explicitly filtered out |
| **Result Ordering** | Random (as crawled) | Sorted by deadline urgency |
| **Search Recency** | Last year (qdr:y) | Last month (qdr:m) |
| **Query Count** | 38 | 46 |
| **Query Keywords** | "2026" "open" "active" | "currently accepting" "open until" "bid opportunity" + above |

---

## Expected Results After Implementation

### Before (Old Pipeline)
```
candidates.jsonl (50 records):
- NYC RFP due 03/11/26 ✓
- April 2025 RFP (PAST) ❌
- 2023 Cloud RFP (OLD) ❌
- 2022 PDF RFP (OLD) ❌
- Feb 2021 MDTA RFP (VERY OLD) ❌
- 2013 CUNY doc (ANCIENT) ❌
- [Many others with mixed dates]
```

### After (New Pipeline)
```
candidates.jsonl (15-20 active RFPs):
- NYC RFP due 03/11/26 ✓ status: open
- May RFP due 05/15/26 ✓ status: open
- June RFP due 06/22/26 ✓ status: open
- [Only active, future-deadline RFPs]
- [Sorted by how soon they're due]
```

---

## Troubleshooting

### Problem: "AttributeError: extract_due_date not found"
**Solution:** Make sure `pipeline.py` imports from `extract_enhanced`, not `extract`:
```python
from .extract_enhanced import extract_due_date_strict, ...
```

### Problem: "All RFPs are being filtered out"
**Possible causes:**
1. Date extraction not finding valid dates → add debug logging
2. All results marked as "closed" → check CLOSED_STATUS_KEYWORDS regex
3. RFP detection too strict → verify STRONG_RFP_MARKERS pattern

**Debug:** Add to pipeline.py:
```python
print(f"Before filtering: {len(records)} records")
filtered = apply_filtering_pipeline(records)
print(f"After filtering: {len(filtered)} records")
```

### Problem: "Too many results being kept"
**Solution:** Adjust in `config/queries.yaml`:
```yaml
recency_tbs: qdr:w  # Change from qdr:m to qdr:w (last week only)
```

---

## Next Phase Recommendations

### Phase 1 (Done) ✅
- Stricter date validation
- RFP status detection
- Filtering pipeline

### Phase 2 (Optional) - LLM Enhancement
Use `extract_with_llm.py` with Claude to:
- Verify "open" vs "closed" status from full text
- Extract exact deadline dates from complex formats
- Validate organization names
- Flag false positives

### Phase 3 (Optional) - Weekly Automation
- Set up scheduled weekly runs
- Track RFP changes (new, updated deadlines)
- Alert on high-priority upcoming deadlines

---

## File Summary

| File | Purpose | Status |
|------|---------|--------|
| `extract_enhanced.py` | **New** strict extraction with date/status validation | ✅ Created |
| `filters.py` | **New** post-processing filtering pipeline | ✅ Created |
| `models.py` | Updated with new fields (`rfp_status`, `due_date_valid`, `recency_score`) | ✅ Updated |
| `pipeline.py` | Updated to use `extract_enhanced` and apply filtering | ✅ Updated |
| `config/queries.yaml` | Enhanced with 46 queries + monthly recency | ✅ Updated |
| `extract.py` | **Old** extraction logic (kept as reference) | - Old version |

---

## Support

For issues or enhancements:
1. Check DATE_PATTERN regex if dates aren't being extracted
2. Check OPEN_STATUS_KEYWORDS and CLOSED_STATUS_KEYWORDS for status detection
3. Check STRONG_RFP_MARKERS and RETIREMENT_CONTEXT for RFP detection strictness
4. Run individual test queries to debug specific RFPs
