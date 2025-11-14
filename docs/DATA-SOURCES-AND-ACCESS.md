# Gridiron-Yampylytics - Data Sources and Access

**Date:** 2025-11-14
**Status:** ✅ FULLY REPRODUCIBLE - All data can be rebuilt from scratch
**Architecture:** 2 loaders + 1 unified script

---

## Overview

This project follows a **fully reproducible data architecture**. Every data source can be acquired from scratch using documented scripts.

**Key Principle:** If you clone this repo, you can rebuild all data by running one command:
```bash
uv run python -m scripts.load_all_data
```

---

## Quick Start (Fresh Clone)

```bash
# Clone repo
git clone <repo-url>
cd gridiron-yampylytics

# Install dependencies
uv sync

# Load all data (10-15 minutes)
uv run python -m scripts.load_all_data

# Result: 3.1M+ rows of NFL data, fully reproducible
```

---

## Data Sources

We have **2 primary data sources**, both with reproducible loaders:

### 1. nflreadpy (10 datasets)
**Source:** nflverse Python package (https://github.com/nflverse/nflreadpy)
**Loader:** `scripts/cache_nflreadpy_data.py`
**Coverage:** 1999-2025 (varies by dataset)
**Status:** ✅ Reproducible

**Available datasets:**

| Dataset | Function | Coverage | Rows |
|---------|----------|----------|------|
| Play-by-play | `load_pbp()` | 1999-2025 (26 seasons) | 1.25M |
| Player stats | `load_player_stats()` | 2012-2025 (13 seasons) | 465K |
| Rosters | `load_rosters()` | 2006-2025 (19 seasons) | 139K |
| Schedules | `load_schedules()` | 1999-2025 (26 seasons) | 7.2K |
| Injuries | `load_injuries()` | 2009-2025 (auto-detected) | 84K |
| Depth charts | `load_depth_charts()` | 2017-2025 (8 seasons) | 1.09M |
| Draft picks | `load_draft_picks()` | 1967-2025 (58+ drafts) | 12.6K |
| Combine | `load_combine()` | 2000-2024 (24+ years) | 8.6K |
| Contracts | `load_contracts()` | 2000s-2025 (48.6K contracts) | 48K |
| Player IDs | `load_ff_playerids()` | All (17K+ players) | 17K |

**Usage:**
```bash
# Cache all datasets locally as CSV/Parquet
uv run python -m scripts.cache_nflreadpy_data --all

# Or specific datasets/seasons
uv run python -m scripts.cache_nflreadpy_data --dataset pbp --seasons 2024
```

**Output location:** `data/cached/nflreadpy/`

---

### 2. GM Executives (32 teams)
**Source:** Pro Football Reference
**Loader:** `scripts/download_gm_data.py`
**Coverage:** 1960-2025 (all 32 NFL teams)
**Status:** ✅ Reproducible

**Usage:**
```bash
# Scrape all 32 teams (~3 minutes with Selenium)
uv run python -m scripts.download_gm_data

# Retry failed teams
uv run python -m scripts.retry_failed_gm_data --all
```

**Output location:** `data/raw/executives/`

**Fields:** Person, Teams, From, To, Titles, Notes

---

### 3. Draft Value Charts (Reference Data)
**Source:** Static reference data (tracked in git)
**Location:** `data/reference/draft_value_charts/`
**Status:** ✅ Committed to git

**Available charts:**
1. **Jimmy Johnson** - Classic chart (Pick 1 = 3000 points)
2. **Rich Hill** - Modern recalibration (Pick 1 = 1000 points)
3. **Fitzgerald-Spielberger** - Alternative methodology (Pick 1 = 3000 points)
4. **Harvard** - Empirically derived (Pick 1 = 494.6 points)

**Usage:**
```python
import pandas as pd
jj = pd.read_csv('data/reference/draft_value_charts/jimmy_johnson_draft_values.csv')
```

---

## Unified Loader

**Script:** `scripts/load_all_data.py`

Runs both data loaders sequentially:
1. nflreadpy cache (10 datasets)
2. GM executives scraper (32 teams)

**Usage:**
```bash
uv run python -m scripts.load_all_data
```

**Runtime:** ~10-15 minutes (varies by network speed)

---

## Data Coverage Timeline

```
1960  1967  1999  2006  2009  2012  2017  2024  2025
 |     |     |     |     |     |     |     |     |
 [GM tenure -----------------------------------------> ] ✅ Scraper (PFR)
       [Draft picks ---------------------------------> ] ✅ nflreadpy
             [PBP --------------------------------> ] ✅ nflreadpy (26 seasons)
             [Schedules ---------------------------> ] ✅ nflreadpy (26 seasons)
                   [Rosters -----------------------> ] ✅ nflreadpy (19 seasons)
                         [Injuries ----------------> ] ✅ nflreadpy (auto-detect)
                               [Player stats ------> ] ✅ nflreadpy (13 seasons)
                                     [Depth charts > ] ✅ nflreadpy (8 seasons)
       [Combine ------------------------------------> ] ✅ nflreadpy (2000-2024)
```

**Gap:** 1960-1999 detailed player stats not available (acceptable for modern GM analysis)
**Note:** Contracts coverage is 2000s-2025 (comprehensive post-2010, spotty pre-2010)

---

## Historical Data (Optional)

**Repo:** https://github.com/kendallgillies/NFL-Statistics-Scrape
**Coverage:** 1970-2016 historical stats
**Status:** Not implemented (available if needed)

This repo provides pre-2000 historical data. We deleted the cached version to maintain modern-era focus (2000+). If you need historical GM analysis (1970s-1990s), you would need to:

1. Clone the repo
2. Test if the scraper still works
3. Build a loader script
4. Or commit the cached data to git with documentation

For now, this is documented but not implemented.

---

## Data Architecture Principles

**Every data source must have:**
1. ✅ Documented acquisition method (loader script, API, etc.)
2. ✅ Ability to update the data
3. ✅ Transparent, verifiable sourcing

**"Cached = Done" is an anti-pattern** - Having data on disk is not the same as being able to reproduce that data.

---

## Cleanup History

### Deleted (Total: 8.2 GB)

**2025-10-31:**
- nfldata repo (7.2 GB) - Replaced by nflreadpy
- NFL_Scraper repo (349 MB) - Deleted loader
- historical-nfl-draft-data repo (6.5 MB) - Outdated
- cached nfl-draft-data (21 MB) - Replaced by nflreadpy

**2025-11-14:**
- cached_nfl_stats (209 MB) - Redundant with nflreadpy
- cached_nfl_scraper (256 MB) - Redundant with nflreadpy
- cached_historical_stats (94 MB) - Modern-era focus

**Result:** 8.2 GB → ~3 MB reference data (99.96% reduction)

---

## Project Structure

```
gridiron-yampylytics/
├── data/
│   ├── cached/           # Generated by loaders (excluded from git)
│   │   └── nflreadpy/    # 10 datasets cached locally
│   ├── raw/              # Generated by scrapers (excluded from git)
│   │   └── executives/   # 32 GM CSV files
│   ├── reference/        # Static data (tracked in git)
│   │   └── draft_value_charts/
│   └── manifest.json     # Data inventory
├── scripts/
│   ├── cache_nflreadpy_data.py   # Loader 1
│   ├── download_gm_data.py       # Loader 2
│   ├── retry_failed_gm_data.py   # Retry utility
│   └── load_all_data.py          # Unified loader
├── docs/
│   └── DATA-SOURCES-AND-ACCESS.md  # This file
└── src/
    └── gridiron_yampylytics/  # Analysis code
```

**Note:** `data/` at project root is the standard Python layout. Source code in `src/` references data using relative paths like `../data/cached/`. This keeps a clean separation and doesn't interfere with Python imports.

---

## Next Phase: Data Transformation

**Ready to build:**
1. GM data combiner (merge 32 CSVs into single table)
2. Coach tenure extractor (from schedules)
3. RAS score calculator (from combine data)
4. SQL database loader (for exploration)

**Status:** ✅ Data acquisition COMPLETE - ready for transformation phase!
