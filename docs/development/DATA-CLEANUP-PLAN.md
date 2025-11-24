# Data Cleanup Plan - Removing Non-Reproducible Cached Datasets

**Date:** 2025-10-31
**Issue Identified:** "Cached = Done" decisions - kept data without loaders

---

## Problem Summary

During data acquisition phase, we made decisions to keep 3 cached datasets (559 MB total) **without ensuring reproducible loaders existed**. This violates the project principle of reproducibility.

**The "Cached = Done" Mistakes:**

1. **cached_nfl_stats (209 MB)** - Kept because it had pre-aggregated fields, not because data is unique
2. **cached_nfl_scraper (256 MB)** - Deleted the loader repo but kept the cached data (impossible to update!)
3. **cached_historical_stats (94 MB)** - Kept "just in case" without building a loader

**Impact:** Anyone cloning the repo cannot reproduce these 559 MB of data.

---

## Agent Analysis Results

The nfl-data-expert agent analyzed each cached dataset:

### cached_nfl_stats (209 MB)
- **Source:** Unknown
- **Coverage:** 2012-2024 (player/team stats with 468+ fields)
- **Replaceable?** YES - nflreadpy provides `load_player_stats()` with raw data
- **Needed?** NO - Pre-aggregated fields are convenient but not unique
- **Loader available?** NO - Source unknown
- **Recommendation:** **REMOVE** - Build aggregations from nflreadpy instead

### cached_nfl_scraper (256 MB)
- **Source:** NFL.com (via deleted NFL_Scraper repo)
- **Coverage:** 2017-2025 (play-by-play, 449 game files)
- **Replaceable?** YES - nflreadpy provides `load_pbp()` covering 1999-2025
- **Needed?** NO - nflreadpy has BETTER coverage (1999 vs 2017 start)
- **Loader available?** NO - Repo was deleted
- **Recommendation:** **REMOVE** - Use nflreadpy PBP instead

### cached_historical_stats (94 MB)
- **Source:** NFL-Statistics-Scrape repo (still exists)
- **Coverage:** 1970-2016 (historical game logs, career stats)
- **Replaceable?** NO - Fills 1970-1999 gap (nflreadpy starts at 1999)
- **Needed?** DEPENDS - Only if analyzing pre-2000 GMs
- **Loader available?** MAYBE - Repo exists but untested
- **Recommendation:** **CONDITIONAL**
  - Modern era focus (2000+)? → REMOVE
  - Historical analysis (1970+)? → BUILD LOADER or COMMIT TO GIT

---

## Recommended Action Plan

### Phase 1: Remove Redundant Cached Data (465 MB)

**Delete these directories:**
```bash
rm -rf src/cached_data/NFL\ Stats\ 2012-2024/
rm -rf src/cached_data/NFL_Scraper/
```

**Rationale:**
- Both datasets are fully replaceable by nflreadpy
- nflreadpy has equal or better coverage
- Removes 465 MB of non-reproducible data
- Simplifies project to 2 clear loaders

### Phase 2: Decide on Historical Data (94 MB)

**Option A: Remove (Recommended for modern GM analysis)**
```bash
rm -rf src/cached_data/NFL-Statistics-Scrape/
```
- Focus analysis on salary cap era (2000+)
- Most relevant GM decisions are post-2000
- Removes final 94 MB of non-reproducible data

**Option B: Build Loader (If analyzing historical GMs)**
1. Clone repo: `git clone https://github.com/kendallgillies/NFL-Statistics-Scrape`
2. Test if scraper still works
3. If works: Document and add to `scripts/`
4. If broken: Fix it OR commit cached data to git with warning

### Phase 3: Update Documentation

**Files to update:**
- `data/manifest.json` - Remove cached dataset entries
- `docs/DATA-SOURCES-AND-ACCESS.md` - Remove cached sections
- `.gitignore` - Remove `src/cached_data/` exclusion (directory won't exist)
- `README.md` - Update with 2-loader architecture

**New manifest structure:**
```json
{
  "data_sources": {
    "nflreadpy": {
      "loader": "scripts/cache_nflreadpy_data.py",
      "coverage": "10 datasets, 1999-2025",
      "status": "reproducible"
    },
    "gm_executives": {
      "loader": "scripts/download_gm_data.py",
      "coverage": "32 teams, 1960-2025",
      "status": "reproducible"
    }
  }
}
```

### Phase 4: Create Unified Loader

**New script:** `scripts/load_all_data.py`

```python
"""Load all NFL data sources for gridiron-yampylytics.

This unified script calls all data acquisition scripts to build
a complete dataset from scratch.

Usage:
    uv run python -m scripts.load_all_data
"""
import subprocess
import sys

def main():
    print("="*80)
    print("LOADING ALL NFL DATA SOURCES")
    print("="*80)

    # 1. Load nflreadpy datasets (10 datasets)
    print("\n[1/2] Loading nflreadpy data...")
    result = subprocess.run([
        "uv", "run", "python", "-m",
        "scripts.cache_nflreadpy_data", "--all"
    ])
    if result.returncode != 0:
        print("❌ nflreadpy cache failed")
        sys.exit(1)

    # 2. Scrape GM executives
    print("\n[2/2] Scraping GM executives...")
    result = subprocess.run([
        "uv", "run", "python", "-m",
        "scripts.download_gm_data"
    ])
    if result.returncode != 0:
        print("❌ GM scraper failed")
        sys.exit(1)

    print("\n" + "="*80)
    print("✅ ALL DATA LOADED SUCCESSFULLY")
    print("="*80)
    print("\nData locations:")
    print("  - nflreadpy: data/cached/nflreadpy/")
    print("  - GM executives: data/raw/executives/")

if __name__ == "__main__":
    main()
```

---

## Benefits of Cleanup

**Before cleanup:**
- 2 reproducible loaders
- 3 non-reproducible cached datasets (559 MB)
- Confusing mix of loader vs cached data
- Cannot rebuild from scratch

**After cleanup:**
- 2 reproducible loaders
- 0 non-reproducible cached datasets
- Clean architecture
- Can rebuild everything from scratch
- Saves 465-559 MB

---

## Implementation Status

- [x] Phase 1: Remove cached_nfl_stats (COMPLETED 2025-11-14)
- [x] Phase 1: Remove cached_nfl_scraper (COMPLETED 2025-11-14)
- [x] Phase 2: Decide on cached_historical_stats (COMPLETED - Deleted, modern-era focus)
- [x] Phase 3: Update manifest.json (COMPLETED 2025-11-14)
- [ ] Phase 3: Update DATA-SOURCES-AND-ACCESS.md
- [x] Phase 3: Update .gitignore (Already configured)
- [x] Phase 4: Create load_all_data.py script (COMPLETED 2025-11-14)
- [ ] Final: Test fresh clone can rebuild all data
- [ ] Final: Commit and push cleaned repo

**Note:** Historical stats repo (https://github.com/kendallgillies/NFL-Statistics-Scrape)
is documented in manifest.json for future use if historical GM analysis (pre-2000) is needed.

---

## Key Lesson Learned

**"Cached = Done" is an anti-pattern for reproducible data projects.**

Having data on disk is not the same as being able to reproduce that data. Every data source must have:
1. A documented acquisition method (loader script, API call, etc.)
2. The ability to update the data
3. Transparent, verifiable sourcing

Pre-aggregated data from unknown sources traded transparency for convenience. The correct approach is:
- Keep raw data acquisition reproducible
- Build aggregations in code (visible, testable, updatable)
- Avoid "black box" cached datasets
