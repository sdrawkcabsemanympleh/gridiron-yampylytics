# Data Gaps to Fill

Based on review of all existing repos and datasets, here are the critical gaps we need to address:

## 1. GM/Coach Tenure Data ⚠️ CRITICAL

**Status:** Not found in any existing repo/dataset

**What we need:**
- GM name, team, start year, end year
- Head coach name, team, start year, end year
- Ideally: other executives (President, etc.)

**Source:** Pro Football Reference has this!
- Directory: `https://www.pro-football-reference.com/executives/`
- Team pages: `https://www.pro-football-reference.com/teams/{team}/executives.htm`
- Coaches: `https://www.pro-football-reference.com/coaches/`

**Options:**
1. **Manual CSV** - Create for key GMs (2010-present) as starter
2. **Scrape PFR** - Build scraper for executive/coach pages
3. **Find existing dataset** - Search Kaggle/GitHub more thoroughly

**Priority:** HIGH - We can't do GM analytics without this!

---

## 2. RAS (Relative Athletic Score) Data

**Status:** Not found in any existing repo/dataset

**What we need:**
- RAS scores by player (0-10 scale)
- Calculated from combine metrics

**Source Options:**
1. Calculate ourselves from combine data (we have this via nflreadpy)
2. Find existing RAS dataset on GitHub
3. Scrape MockDraftable (has similar percentile scores)

**RAS Calculation:**
- Standardize each combine metric by position
- Convert to 0-10 scale
- Weight and combine metrics
- Formula available: https://relativeathleticscores.com/

**Priority:** MEDIUM - Nice to have, can calculate from combine data

---

## 3. Contract Data Details

**Status:** nflreadpy has `load_contracts()` but need to verify what it includes

**What we need:**
- Cap hit by player/year
- Dead money by player/year
- Contract years remaining
- Team cap space by year
- Team dead money totals by year

**Need to verify:**
- What does nflreadpy.load_contracts() actually provide?
- Do we need to supplement with Spotrac scraper?

**Test command:**
```python
import nflreadpy as nfl
contracts = nfl.load_contracts()
print(contracts.columns)
print(contracts.head())
```

**Priority:** HIGH - Critical for contract efficiency analysis

---

## 4. Data Range Verification

**Status:** Need to spot-check actual date ranges in cached datasets

**Datasets to verify:**
1. **NFL Stats 2012-2024** (cached) - Does it really go through 2024?
2. **NFL_Scraper** (cached) - Claims through 2025 Week 7, verify
3. **nfl-draft-data** (cached) - Claims 1967-2021, verify

**Method:**
- Load each CSV
- Check min/max year columns
- Compare to file name claims

**Priority:** MEDIUM - Good housekeeping

---

## Next Actions

### Immediate (This Session)
1. ✅ Confirm we have Pro Football Reference executive pages available
2. ⬜ Test nflreadpy.load_contracts() to see what we get
3. ⬜ Search GitHub/Kaggle for existing GM/coach tenure datasets
4. ⬜ Research RAS calculation feasibility

### Short Term
5. Build GM/coach scraper for PFR (or create manual CSV)
6. Implement RAS calculation from combine data
7. Verify date ranges in cached datasets
8. Document what contract data we have vs need

### If Needed
9. Adapt Spotrac scraper for additional contract details
10. Find or create draft value charts CSV
