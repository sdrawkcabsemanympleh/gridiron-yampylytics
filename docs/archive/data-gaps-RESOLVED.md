# Data Gaps - Status & Solutions

## Summary

✅ **GREAT NEWS**: We have solutions for all critical data gaps!

---

## 1. GM/Coach Tenure Data ✅ PARTIALLY RESOLVED

### Coach Data: ✅ FOUND
**Source:** nfldata `games.csv`
- Columns: `away_coach`, `home_coach`
- Coverage: 2006-present (Feb 2020 addition to dataset)
- **Action:** Extract unique coach-team-year combinations from game data

**Example extraction:**
```python
import pandas as pd
games = pd.read_csv('nfldata/data/games.csv')
coaches = games.groupby(['season', 'home_team', 'home_coach']).size().reset_index()
# Combine with away_coach data, deduplicate, get tenure ranges
```

### GM Data: ⚠️ NEEDS SCRAPING
**Source:** Pro Football Reference
- URL: `https://www.pro-football-reference.com/executives/`
- Team pages: `https://www.pro-football-reference.com/teams/{team}/executives.htm`
- **Good news:** Pages have CSV download links!
- **Action:** Build simple downloader script (not scraper - just download CSVs)

**Priority:** HIGH for GM analytics, but coach data gets us started

---

## 2. Contract Data ✅ RESOLVED (with limitations)

### What We Have: nflreadpy.load_contracts()
- ✅ 48,536 contracts (years 0-2025)
- ✅ APY (Average Per Year)
- ✅ Guaranteed money
- ✅ APY as % of cap
- ✅ Total contract value
- ✅ Contract length (years)
- ✅ Player IDs for linking

### What's Missing:
- ❌ Yearly cap hit breakdown
- ❌ Dead money by year
- ❌ Team cap space by year

### Solution:
**Option A:** Start with what we have - Can analyze:
- Rookie contract efficiency (draft to guaranteed $)
- Contract value by GM
- Position spending patterns

**Option B (if needed later):** Add Spotrac scraper for detailed cap/dead money

**Decision:** Start with Option A, add Option B only if metrics require it

---

## 3. RAS (Relative Athletic Score) ✅ CAN CALCULATE

### Approach: Calculate from combine data
We have combine data via nflreadpy.load_combine()

**RAS Formula:**
1. Get combine metrics by position (40-time, bench, vertical, broad, 3-cone, shuttle)
2. Calculate position-specific percentiles for each metric
3. Convert to 0-10 scale
4. Apply position-specific weighting
5. Average to final RAS score

**Reference:** https://relativeathleticscores.com/about/

**Implementation:**
```python
# Pseudocode
combine = nfl.load_combine()
for position in positions:
    metrics = get_position_metrics(combine, position)
    percentiles = calculate_percentiles(metrics)
    ras = apply_weights(percentiles, position)
```

**Priority:** MEDIUM - Nice to have, straightforward to implement

---

## 4. Data Range Verification ✅ ACTION NEEDED

### Datasets to Verify:
1. **NFL Stats 2012-2024** (cached, 209 MB)
2. **NFL_Scraper** (cached, 256 MB) - Claims through 2025 Week 7
3. **nfl-draft-data** (cached, 21 MB) - Claims 1967-2021

### Action:
Create verification script to check actual date ranges:
```python
import pandas as pd

datasets = {
    'NFL Stats 2012-2024': 'path/to/file.csv',
    'NFL_Scraper': 'path/to/file.csv',
    'nfl-draft-data': 'path/to/file.csv'
}

for name, path in datasets.items():
    df = pd.read_csv(path)
    year_col = find_year_column(df)
    print(f"{name}: {df[year_col].min()} - {df[year_col].max()}")
```

**Priority:** LOW - Good housekeeping, not blocking

---

## Action Plan

### Immediate (This Session)
1. ✅ Test nflreadpy contracts - DONE
2. ✅ Find coach data - DONE (in games.csv!)
3. ✅ Identify GM data source - DONE (PFR with CSV downloads)
4. ⬜ Document RAS calculation approach
5. ⬜ Create PFR GM data downloader script

### Short Term
6. Extract coach tenure from games.csv
7. Download GM data from PFR
8. Implement RAS calculation
9. Verify cached dataset date ranges

### Medium Term
10. Build unified GM/Coach tenure dataset
11. Decide if we need Spotrac for detailed cap analysis
12. Create data validation tests

---

## Key Findings

1. **Coach data is already available** in nfldata games.csv (2006-present)
2. **GM data is accessible** via PFR CSV downloads (no complex scraping needed)
3. **Contract data is sufficient** for most GM analysis without detailed cap breakdown
4. **RAS is calculable** from combine data we already have access to

## Bottom Line

**We can proceed with GM analytics!** All critical data is either available or easily obtainable.

No major blockers. 🎉
