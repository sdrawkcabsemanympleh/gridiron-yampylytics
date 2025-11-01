# Gridiron-Yampylytics - Data Sources and Access Patterns

**Date:** 2025-10-31
**Status:** ✅ Phase 1 COMPLETE - All sources mapped, verified, and cleaned up
**Cleanup:** ✅ COMPLETE - 7.6 GB removed (93% reduction)

---

## Overview

This document categorizes all NFL data sources by **acquisition method** and documents the **access pattern** for loading raw data to this machine.

**Key Terminology:**
- **Loading:** Pulling raw, untransformed data to this machine
- **Transformation:** Converting raw data into analysis-ready format (separate phase)

---

## Data Source Categories

### 1. Python Package (nflreadpy)
**Acquisition:** `uv add nflreadpy` (already installed)
**Access Pattern:** Function calls that download data on-demand
**Update Frequency:** Daily (automated by nflverse)
**Size:** 1.5 MB (package), data loaded as needed

### 2. Git Repository (nfldata)
**Acquisition:** `git clone https://github.com/nflverse/nfldata`
**Access Pattern:** `git pull` to get latest commits
**Update Frequency:** Daily (automated by nflverse)
**Size:** 7.2 GB (with git history), ~10 MB (data files only)
**Status:** ⚠️ **Recommended for deletion** - use nflreadpy instead

### 3. Active Scrapes (Run Scripts)
**Acquisition:** Run Python scraper scripts
**Access Pattern:** Execute script, wait for completion, save to `data/raw/`
**Update Frequency:** Manual (run when needed)
**Size:** Varies by source

### 4. Cached Datasets (Pre-scraped)
**Acquisition:** Already on disk
**Access Pattern:** Read CSV files directly from `src/cached_data/`
**Update Frequency:** Static (snapshot from acquisition date)
**Size:** 576 MB total

---

## Detailed Source Inventory

### **Category 1: Python Package (On-Demand Loading)**

#### nflreadpy
**Source:** `pip install nflreadpy` (nflverse official package)
**Location:** Python site-packages (managed by uv)
**Verified Coverage:** Multiple datasets (see below)

| Function | Data Type | Coverage | Verified |
|----------|-----------|----------|----------|
| `load_pbp()` | Play-by-play | 1999-2025 | ✅ |
| `load_player_stats()` | Weekly/seasonal stats | 2012-2025 | ✅ |
| `load_rosters()` | Weekly rosters | 2006-2025 | ✅ |
| `load_draft_picks()` | Draft history | 1967-2025 | ✅ |
| `load_combine()` | Combine results | 2000-2024 | ✅ |
| `load_contracts()` | Contracts (48K) | 2000s-2025 | ✅ |
| `load_ids()` | Player ID mappings | All | ✅ |
| `load_schedules()` | Game schedules | 1999-2025 | ✅ |
| `load_injuries()` | Injury reports | Recent | ✅ |
| `load_depth_charts()` | Team depth charts | 2017-2025 | ✅ |

**Access Pattern:**
```python
import nflreadpy as nfl
# Data downloads automatically when called
pbp = nfl.load_pbp([2024])  # Returns Polars DataFrame
draft = nfl.load_draft_picks()
```

**Loading Strategy:** ✅ **No loader needed** - built-in functions handle everything

---

### **Category 2: Git Repository (Pull Latest)**

#### nfldata
**Source:** `https://github.com/nflverse/nfldata`
**Location:** `C:/Users/shays/code/nfldata/`
**Size:** 7.2 GB (with git history), ~10 MB (data files)
**Status:** ⚠️ **RECOMMENDED FOR DELETION** - nflreadpy provides same data

**Key Files:**
- `data/games.csv` - Game results with **coach names** (2006-2025)
- `data/draft_picks.csv` - Draft data (2000-2025)
- `data/draft_values.csv` - Jimmy Johnson & Rich Hill trade value charts
- `data/rosters.csv` - Player rosters
- `data/trades.csv` - Trade history
- `data/standings.csv` - Season standings
- `data/teams.csv` - Team info and codes

**Access Pattern:**
```bash
cd C:/Users/shays/code/nfldata
git pull  # Get latest data
# Then read CSVs directly
```

```python
import pandas as pd
games = pd.read_csv('C:/Users/shays/code/nfldata/data/games.csv')
```

**Loading Strategy:**
- **Option A:** Delete repo, use `nflreadpy.load_schedules()` instead
- **Option B:** Keep repo, run `git pull` before analysis
- **Recommendation:** Option A (save 7.2 GB, same data via nflreadpy)

---

### **Category 3: Active Scrapes (Run Scripts)**

#### 3A. GM/Executive Data (PFR) ✅ **COMPLETE**
**Source:** Pro Football Reference (https://www.pro-football-reference.com/teams/{team}/executives.htm)
**Script:** `scripts/download_gm_data.py`
**Coverage:** 1960-2025 (32/32 teams)
**Verified:** ✅ Yes (2025-10-31)

**Access Pattern:**
```bash
cd gridiron-yampylytics
uv run python -m scripts.download_gm_data  # ~3 minutes (Selenium + delays)
# Outputs to: data/raw/executives/*.csv
```

**Loading Strategy:** ✅ **Complete** - Script automatically updates manifest.json
**Update Frequency:** Run manually when GM changes occur (typically off-season)

---

#### 3B. NFL_Scraper (NFL.com Play-by-Play)
**Source:** NFL.com
**Repo:** `https://github.com/KeoniM/NFL_Scraper`
**Location:** `C:/Users/shays/code/NFL_Scraper/`
**Size:** 349 MB (repo with code + old data)
**Status:** ⚠️ **Data already cached** - can delete repo

**Access Pattern:**
```bash
cd C:/Users/shays/code/NFL_Scraper
# Would run scraper script here (need to investigate repo structure)
```

**Loading Strategy:**
- **Current:** Use cached data (see Category 4)
- **Future:** If need updates beyond 2025 Week 7, investigate repo scraper
- **Recommendation:** Delete repo (save 349 MB), use cached data

---

#### 3C. NFL-Statistics-Scrape (NFL.com Historical Stats)
**Source:** NFL.com
**Repo:** `https://github.com/kendallgillies/NFL-Statistics-Scrape`
**Location:** `C:/Users/shays/code/NFL-Statistics-Scrape/`
**Size:** 182 KB (scraper code)
**Coverage:** 1970-2016 (historical)

**Access Pattern:**
```bash
cd C:/Users/shays/code/NFL-Statistics-Scrape
# Would run scraper script here
```

**Loading Strategy:**
- **Current:** Use cached data (see Category 4)
- **Future:** Not needed (nflreadpy covers recent data)
- **Recommendation:** Keep cached data, delete repo (save 182 KB)

---

#### 3D. nflscrapy (PFR Comprehensive)
**Source:** Pro Football Reference
**Repo:** `https://github.com/blnkpagelabs/nflscraPy`
**Location:** `C:/Users/shays/code/nflscrapy/`
**Size:** 304 KB
**Status:** ✅ **Keep** - proven PFR scraper, useful reference

**What it scrapes:**
- Box scores
- Metadata
- Snap counts
- FiveThirtyEight data
- Uses respectful delays (3.5-5.5s)

**Access Pattern:**
```python
# Example usage (consult repo README for specifics)
from nflscraPy import stats
data = stats.get_boxscore_stats(boxscore_url)
```

**Loading Strategy:** ✅ **Reference only** - keep for scraping patterns, not actively using

---

#### 3E. scrape_pfr (PFR Various Data)
**Source:** Pro Football Reference
**Repo:** `https://github.com/ewelchman/scrape_pfr`
**Location:** `C:/Users/shays/code/scrape_pfr/`
**Size:** 217 KB
**Status:** ✅ **Keep** - useful PFR scraping reference (uses Selenium)

**What it scrapes:**
- Play-by-play
- Box scores
- Injury reports

**Loading Strategy:** ✅ **Reference only** - keep for scraping techniques

---

#### 3F. Spotrac Salary Data
**Source:** Spotrac.com
**Repo:** `https://github.com/mipsbe/Spotrac.com-NFL-Scrap`
**Location:** `C:/Users/shays/code/Spotrac.com-NFL-Scrap/`
**Size:** 165 KB
**Status:** ⏭️ **Future use** - if need detailed cap data

**What it scrapes:**
- Player salaries by year
- Cap hits
- Dead money
- Bonuses

**Loading Strategy:** ⏭️ **Not needed yet** - nflreadpy contracts sufficient for now

---

### **Category 4: Cached Datasets (Static CSVs)**

All cached datasets verified 2025-10-31 by nfl-data-expert agent.

---

#### 4A. NFL Stats 2012-2024
**Location:** `src/cached_data/NFL Stats 2012-2024/`
**Size:** 209 MB
**Files:** 8 CSV files
**Source:** ❓ Unknown (appears to be aggregated nflfastR-style data)
**Verified Coverage:** 2012 Week 1 - 2024 Super Bowl (Week 22) ✅

**Files:**
- `weekly_player_stats_offense.csv` (58,630 rows, 2012 W12 - 2024 W15)
- `weekly_player_stats_defense.csv` (117,994 rows, 2012 - 2024 W19)
- `weekly_team_stats_offense.csv` (7,089 rows, 2012 W1 - 2024 W22) **MOST COMPLETE**
- `weekly_team_stats_defense.csv` (7,089 rows, 2012 W1 - 2024 W22) **MOST COMPLETE**
- `yearly_player_stats_offense.csv` (7,134 rows)
- `yearly_player_stats_defense.csv` (16,149 rows)
- `yearly_team_stats_offense.csv` (583 rows)
- `yearly_team_stats_defense.csv` (583 rows)

**Schema:** 468+ fields including passing, rushing, receiving, tackles, coverage, fantasy points, advanced metrics

**Data Quality Issues:**
- Player offensive stats start at 2012 Week 12 (missing Weeks 1-11)
- Player stats incomplete for 2024 Weeks 16-22
- Team stats are MOST COMPLETE (through 2024 Super Bowl)

**Access Pattern:**
```python
import pandas as pd
team_off = pd.read_csv('src/cached_data/NFL Stats 2012-2024/weekly_team_stats_offense.csv')
```

**Loading Strategy:** ✅ **Use as-is** - Best team-level stats for 2012-2024
**Recommendation:** Keep for team analysis, supplement with nflreadpy for player stats

---

#### 4B. NFL_Scraper (Play-by-Play)
**Location:** `src/cached_data/NFL_Scraper/`
**Size:** 256 MB
**Files:** 449 CSV files (one per game)
**Source:** NFL.com (matches `C:/Users/shays/code/NFL_Scraper/` repo)
**Verified Coverage:** 2017 Hall of Fame Game (8/3/2017) - 2025 Week 7 (10/20/2025) ✅

**Latest Game:** 2025 Week 7, Monday 10/20/2025 - Texans @ Seahawks

**Structure:**
```
NFL_Scraper/
├── 2017_plays.csv through 2025_plays.csv (season aggregates)
├── 2017-2025_scores.csv (all game scores)
├── Season_plays/new_format/2017-2025_plays_by_week/
└── Season_Scores/
```

**Schema:** Play-level data with down, distance, field position, play type, yards, personnel, scoring

**Access Pattern:**
```python
import pandas as pd
# Season aggregate
pbp_2024 = pd.read_csv('src/cached_data/NFL_Scraper/2024_plays.csv')
# Specific week
week1 = pd.read_csv('src/cached_data/NFL_Scraper/Season_plays/new_format/2024_plays_by_week/2024_week_1_plays.csv')
```

**Loading Strategy:** ✅ **Use as-is** - Most detailed play-by-play for 2017-2025 Week 7
**Recommendation:** Keep - essential for drive analysis and situational football

---

#### 4C. nfl-draft-data
**Location:** `src/cached_data/nfl-draft-data/`
**Size:** 21 MB
**Files:** 5 CSV files
**Source:** `https://github.com/JackLich10/nfl-draft-data` (matches repo)
**Verified Coverage:** Draft 1967-2021 | College stats 2014-2020 ✅
**Status:** ❌ **OUTDATED** - Missing 2022-2024 drafts (3+ years behind)

**Files:**
- `nfl_draft_prospects.csv` (13,355 rows)
- `nfl_draft_profiles.csv` (15,634 rows)
- `college_statistics.csv` (66,673 rows, 2014-2020 only)
- `college_qbr.csv` (2,050 rows)
- `ids.csv` (237 rows)

**Access Pattern:**
```python
import pandas as pd
prospects = pd.read_csv('src/cached_data/nfl-draft-data/nfl_draft_prospects.csv')
```

**Loading Strategy:** ❌ **REPLACE with nflreadpy** - outdated
**Recommendation:** Delete cached data, use `nflreadpy.load_draft_picks()` for 1967-2025 coverage

---

#### 4D. NFL-Statistics-Scrape (Historical)
**Location:** `src/cached_data/NFL-Statistics-Scrape/`
**Size:** 94 MB
**Files:** 19 CSV files
**Source:** NFL.com (matches repo)
**Verified Coverage:** 1970-2016 ✅

**Files:**
- Career stats by position (8 files)
- Game logs by position (11 files, including 39 MB defensive lineman file)

**Schema:** Position-specific career stats and game-by-game logs

**Access Pattern:**
```python
import pandas as pd
qb_logs = pd.read_csv('src/cached_data/NFL-Statistics-Scrape/Game_Logs_Quarterback.csv')
career_rush = pd.read_csv('src/cached_data/NFL-Statistics-Scrape/Career_Stats_Rushing.csv')
```

**Loading Strategy:** ✅ **Use as-is** - Valuable historical data (1970-2016)
**Recommendation:** Keep - fills gap for 1970-2011 era, complements modern datasets

---

## Data Coverage Timeline (Verified)

```
1960  1967  1970    1999  2006  2012  2017  2024  2025
 |     |     |       |     |     |     |     |     |
 [GM tenure (PFR)---------------------------------->  ✅ NEW!
       [Draft (nflreadpy)--------------------------->  ✅
             [Historical Stats--]                      ✅ Cached
             1970-2016
                     [PBP (nflreadpy)--------------->  ✅
                           [Coach (games.csv)------->  ✅
                           [Rosters (nflreadpy)----->  ✅
                                 [Team Stats------->  ✅ Cached (best)
                                       [PBP Cached->  ✅ Most detailed
                                             2024 2025 W7
```

---

## Loading Strategy Summary

| Data Type | Primary Source | Access Method | Loader Needed? |
|-----------|---------------|---------------|----------------|
| **Play-by-play** | nflreadpy | `nfl.load_pbp()` | ❌ No |
| **Player stats** | nflreadpy | `nfl.load_player_stats()` | ❌ No |
| **Team stats** | Cached (NFL Stats 2012-2024) | Read CSV | ✅ Yes (simple) |
| **Draft picks** | nflreadpy | `nfl.load_draft_picks()` | ❌ No |
| **Combine** | nflreadpy | `nfl.load_combine()` | ❌ No |
| **Contracts** | nflreadpy | `nfl.load_contracts()` | ❌ No |
| **GM tenure** | PFR scrape (ours) | Run script | ✅ Script exists |
| **Coach tenure** | nfldata games.csv | Read CSV → transform | ✅ Yes (extract) |
| **Historical stats** | Cached (NFL-Statistics-Scrape) | Read CSV | ✅ Yes (simple) |
| **Detailed PBP** | Cached (NFL_Scraper) | Read CSV | ✅ Yes (simple) |

---

## ✅ Cleanup COMPLETED (2025-10-31)

### Deleted (Total: 7.6 GB) ✅

1. ✅ **nfldata/** (7.2 GB) - DELETED
   - Replaced by: `nflreadpy.load_schedules()` for same data

2. ✅ **NFL_Scraper repo** (349 MB) - DELETED
   - Data preserved in: `src/cached_data/NFL_Scraper/`

3. ✅ **historical-nfl-draft-data/** (6.5 MB) - DELETED
   - Superseded by: nflreadpy draft data

4. ✅ **Cached nfl-draft-data/** (21 MB) - DELETED
   - Replaced by: `nflreadpy.load_draft_picks()` (1967-2025, current)

### Keep

1. **nflreadpy/** (1.5 MB) - Python package, primary data source
2. **scrape_pfr/** (217 KB) - Reference for PFR scraping techniques
3. **nflscrapy/** (304 KB) - Reference for PFR scraping patterns
4. **NFL-Combine-Data/** (1.2 MB) - Potential future use
5. **Spotrac.com-NFL-Scrap/** (165 KB) - Future detailed cap data
6. **Cached NFL Stats 2012-2024/** (209 MB) - Best team stats
7. **Cached NFL_Scraper/** (256 MB) - Detailed play-by-play
8. **Cached NFL-Statistics-Scrape/** (94 MB) - Historical data

**Result:** ~562 MB (down from 8.1 GB) - **93% reduction achieved! ✅**

---

## Loader Implementation Plan

### No Loader Needed (Built-in)
- nflreadpy functions (10 different data types)

### Simple CSV Loaders (Build)
1. **Team stats loader** - Read from `NFL Stats 2012-2024/`
2. **Historical stats loader** - Read from `NFL-Statistics-Scrape/`
3. **Play-by-play detailed loader** - Read from `NFL_Scraper/`
4. **GM data combiner** - Combine 32 executive CSVs into one DataFrame

### Extraction Transformers (Build Later - Data Transformation Phase)
1. **Coach tenure extractor** - Extract from games.csv
2. **RAS calculator** - Calculate from combine data

### Git Pull Scripts (Optional)
- Not needed if we delete nfldata repo
- If keep repo: `cd nfldata && git pull`

---

## Completed Actions ✅

1. ✅ Document sources and access patterns (this file)
2. ✅ Update manifest.json with source categorization
3. ✅ Commit documentation to memory
4. ✅ Execute 7.6 GB cleanup plan - **COMPLETE!**

## Next Actions

5. ⬜ Build 4 simple CSV loaders
6. ⬜ Test all loaders
7. ⬜ Move to data transformation phase

---

## Bottom Line

**Data Acquisition:** ✅ 100% COMPLETE
**Cleanup:** ✅ COMPLETE (7.6 GB removed, 93% reduction)
**GM Data:** ✅ Complete (32/32 teams, 1960-2025)
**Coach Data:** ✅ Available (2006-2025 via nflreadpy, needs extraction)
**Player/Team Data:** ✅ Excellent coverage (1970-2025)
**Draft/Combine:** ✅ Complete (1967-2025)

**Blockers:** None! Ready to build loaders and move to transformation phase.

**Status:** ⚡ LEAN AND READY - From 8.1 GB bloat to 562 MB of pure, verified data!
