# NFL Data Repositories & Datasets Inventory
**Project:** gridiron-yampylytics
**Date:** 2025-10-27
**Purpose:** Research and inventory of available NFL data sources and tooling

---

## Executive Summary

**Total Repositories Analyzed:** 9
**Total Cached Datasets:** 4
**Combined Repository Size:** ~7.9 GB (7.2 GB is git history in nfldata)
**Cached Data Size:** 576 MB

### Key Findings

1. **nflreadpy** is the modern, actively maintained Python package we should use as primary dependency
2. **nfldata** repo contains valuable reference data but most is git history - data files are only ~10MB
3. **NFL_Scraper** provides current 2025 season data (updated through Week 7)
4. Multiple draft data sources with varying quality and completeness
5. Already have comprehensive cached datasets covering 2012-2025

---

## Repository Analysis

### 1. nfldata (7.2 GB)
**Location:** `C:/Users/shays/code/nfldata`
**Last Updated:** 2025-10-28 (Automated daily updates)
**Language:** R (nflscrapR/nflfastR ecosystem)

#### Size Breakdown
- **Git History:** 7.1 GB (pack file)
- **Actual Data:** ~10 MB
- **Code/Docs:** 64 KB

#### Data Included
Contains curated NFL reference data from Lee Sharpe's nfldata project:
- `draft_picks.csv` (550 KB) - Draft data 2000-present
- `games.csv` (2.1 MB) - Game results 2006-present with betting lines
- `rosters.csv` (1.6 MB) - Player rosters 2006-present
- `officials.csv` (2.0 MB) - Game officials
- `trades.csv` (276 KB) - Trade data 2010-present
- `standings.csv` (54 KB) - Season standings 2002-present
- Reference files: teams, logos, colors, draft values

#### Quality
- **Excellent** - Clean CSVs with documented schemas
- **Player IDs:** Uses Pro Football Reference IDs (pfr_id)
- **Well-maintained:** Daily automated updates
- **Documentation:** Comprehensive DATASETS.md file

#### Recommendation
**Use as Reference** - Download the data files directly (skip git clone to avoid 7GB history). Valuable for:
- Draft pick reference data with PFR player IDs
- Game schedules with betting lines and weather
- Team/color/logo reference data
- Trade history

**Action:** Extract just the `/data` directory CSVs (10MB total)

---

### 2. nflreadpy (1.5 MB)
**Location:** `C:/Users/shays/code/nflreadpy`
**Last Updated:** 2025-10-26
**Language:** Python 3.10+ with Polars
**Status:** Active Development

#### Description
Modern Python port of R's nflreadr package. Official nflverse project.

#### Tooling Included
Full-featured Python package with:
- 20+ load functions for NFL data
- Automatic caching (memory or filesystem)
- Progress tracking for downloads
- Type hints and modern Python conventions
- Uses Polars DataFrames (faster than pandas)

#### Available Data via API
- Play-by-play data (2000-present)
- Player/team statistics (game and season level)
- Schedules, rosters, depth charts
- Draft picks, combine results
- Contracts, injuries, trades
- NextGen stats, FTN charting
- Fantasy football data

#### Quality
- **Excellent** - Professional package with CI/CD
- **Well-documented** - Full API documentation
- **Active:** Latest commit 2 days ago
- **Maintained:** By nflverse organization

#### Recommendation
**PRIMARY DEPENDENCY** - This should be our main data acquisition tool:
- Install as Python dependency: `uv add nflreadpy`
- Use for all programmatic data fetching
- Leverages nflverse's automated data pipelines
- No need to maintain our own scrapers

**Action:** Add to project dependencies and use as primary data source

---

### 3. NFL_Scraper (349 MB repo, 256 MB cached)
**Location:** `C:/Users/shays/code/NFL_Scraper`
**Last Updated:** 2025-10-21 (Week 7 of 2025 season)
**Language:** Python (Selenium + Chrome)

#### Data Included
Play-by-play data scraped from NFL.com:
- Annual files: 2017-2025 (11 MB each year)
- Scores file: 2017-2025 (232 KB)
- Total: 449 CSV files
- **Current through 2025 Week 7**

#### Data Format
CSV files with columns:
- Season, Week, Day, Date
- Teams (Away/Home)
- Quarter, DriveNumber, PlayNumberInDrive
- Play descriptions and outcomes
- No player IDs (uses names only)

#### Quality
- **Good** - Structured play-by-play data
- **Current:** Most recent data available (2025 Week 7)
- **Limitation:** No player IDs, only names
- **Inconsistent:** Names may not match across sources

#### Tooling
Python scraper using Selenium:
- `scraper.py` (65 KB) - Main scraping logic
- `main.py` - Entry point
- Can be run to update data

#### Recommendation
**Use Cached Data, Skip Tooling** - We already have the data cached:
- Use cached files for 2017-2025 play-by-play data
- Don't need to run scraper (nflreadpy covers this)
- Keep cached data for backup/validation
- Good for recent 2025 season data until nflverse updates

**Action:** Keep cached data, archive repository

---

### 4. nfl-draft-data (21 MB repo, 17 MB cached)
**Location:** `C:/Users/shays/code/nfl-draft-data`
**Last Updated:** 2021-05-05 (Data through 2021 draft)
**Language:** R

#### Data Included
Comprehensive draft prospect data:
- `nfl_draft_prospects.csv` (3.3 MB) - 1967-2021 drafts
- `nfl_draft_profiles.csv` (6.9 MB) - Prospect analysis text
- `college_statistics.csv` (6.2 MB) - College stats by season
- `college_qbr.csv` (206 KB) - ESPN QB ratings 2004+
- `ids.csv` (7 KB) - ESPN to nflfastR ID mapping

#### Quality
- **Very Good** - Clean, documented schemas
- **Player IDs:** ESPN player_id and nflfastR IDs
- **Limitation:** Only updated through 2021
- **Rich Data:** Includes college stats and scouting text

#### Recommendation
**Use for Historical Draft Analysis** - Good for:
- Draft data 1967-2021 (4 years old)
- College statistics and QBR
- Prospect profiles with scouting text
- Need to supplement with newer draft data (2022-2025)

**Action:** Keep cached data for historical analysis, supplement with nflreadpy for recent drafts

---

### 5. historical-nfl-draft-data (6.5 MB)
**Location:** `C:/Users/shays/code/historical-nfl-draft-data`
**Last Updated:** 2023-10-02
**Language:** C# (.NET polyglot notebooks)

#### Data Included
Historical draft CSVs:
- Individual draft files: 2015-2023 (per year)
- Compilation: 2015-2022 combined
- Source: Pro Football Reference

#### Quality
- **Good** - Clean PFR data
- **Limitation:** Only 2015-2023 coverage
- **Tooling:** .NET notebooks (not Python)

#### Recommendation
**Skip** - Redundant with other sources:
- nfl-draft-data covers this better (1967-2021)
- nfldata has draft_picks.csv (2000-present)
- Limited coverage (only 9 years)

**Action:** Archive repository, don't use

---

### 6. NFL-Combine-Data (1.2 MB)
**Location:** `C:/Users/shays/code/NFL-Combine-Data`
**Last Updated:** 2018-02-12 (6+ years old)
**Language:** Python (BeautifulSoup)

#### Data Included
Single CSV file:
- `playercombinedata.csv` (807 KB)
- Source: nflcombineresults.com
- Historical combine measurements

#### Quality
- **Outdated** - Last updated 2018
- **Limited:** Single static file
- **Better Source:** nflreadpy has `load_combine()` function

#### Recommendation
**Skip** - Use nflreadpy instead:
- nflreadpy provides current combine data
- This repo is 6+ years outdated
- Scraper may no longer work

**Action:** Archive repository, use nflreadpy.load_combine()

---

### 7. NFL-Statistics-Scrape (182 KB repo, 94 MB cached)
**Location:** `C:/Users/shays/code/NFL-Statistics-Scrape`
**Last Updated:** 2017-06-13 (7+ years old)
**Language:** Python (BeautifulSoup)

#### Cached Data Included
Comprehensive player statistics from NFL.com:
- Basic stats: height, weight, college (2.1 MB)
- Career stats by type: 11 files (16 MB total)
- Game logs by position: 7 files (80 MB total)
- **19 CSV files, 94 MB total**

#### Data Types
Career Statistics:
- Defensive, Passing, Rushing, Receiving
- Field Goals, Punting, Returns, Fumbles
- Offensive Line stats

Game Logs:
- QB, RB, WR/TE, OL, DL, K, P

#### Quality
- **Mixed** - Comprehensive but outdated
- **Historical Value:** Data through ~2017
- **No Updates:** Scraper likely broken
- **Player IDs:** Uses NFL.com URL identifiers

#### Recommendation
**Keep Cached Data for Historical Reference** - Useful for:
- Pre-2017 historical game logs
- Cross-validation with other sources
- Don't rely on for current analysis
- nflreadpy covers this better

**Action:** Keep cached data, archive repository

---

### 8. Spotrac.com-NFL-Scrap (165 KB)
**Location:** `C:/Users/shays/code/Spotrac.com-NFL-Scrap`
**Last Updated:** 2024-11-25 (very recent!)
**Language:** Python

#### Description
Scraper for NFL player salary data from Spotrac.com

#### Quality
- **Unknown** - Haven't executed to see data quality
- **Recently Updated:** Last commit was recent
- **Niche Use Case:** Salary data
- **Alternative:** nflreadpy has `load_contracts()` for contract data

#### Recommendation
**Test and Compare** - Potentially useful for:
- Current salary cap data
- Contract details
- Compare with nflreadpy.load_contracts()
- Keep if provides better/more current salary data

**Action:** Test against nflreadpy contract data, decide based on quality

---

### 9. nflscrapy (301 KB)
**Location:** `C:/Users/shays/code/nflscrapy`
**Last Updated:** 2023-05-06
**Language:** Python

#### Description
Python package for scraping Pro Football Reference:
- Published on PyPI as `nflscraPy`
- Scrapes boxscores, seasons, metadata
- Includes FiveThirtyEight Elo ratings
- Madden ratings scraper

#### Features
- Seasonal gamelogs (2000-present)
- Game metadata (weather, spreads, stadium)
- Expected points calculations
- Snap counts (2012+)
- Season splits
- FiveThirtyEight predictions (1970+)
- Madden ratings (2021+)

#### Quality
- **Good** - Published package
- **Rate Limited:** 3.5-5.5s delays between requests
- **PFR-focused:** Only scrapes Pro Football Reference
- **Alternative:** nflreadpy covers most of this

#### Recommendation
**Skip as Dependency** - Reasons:
- nflreadpy is more comprehensive
- Rate limiting makes it slow
- Redundant with nflreadpy functionality
- May be useful for Madden ratings (niche)

**Action:** Keep for reference, don't use as dependency

---

## Cached Datasets Analysis

### 1. NFL Stats 2012-2024 (209 MB)
**Location:** `C:/Users/shays/code/gridiron-yampylytics/src/cached_data/NFL Stats 2012-2024`

#### Contents (8 CSV files)
Weekly Data:
- `weekly_player_stats_offense.csv` (101 MB)
- `weekly_player_stats_defense.csv` (63 MB)
- `weekly_team_stats_offense.csv` (3.6 MB)
- `weekly_team_stats_defense.csv` (1.7 MB)

Yearly Data:
- `yearly_player_stats_offense.csv` (27 MB)
- `yearly_player_stats_defense.csv` (13 MB)
- `yearly_team_stats_offense.csv` (441 KB)
- `yearly_team_stats_defense.csv` (187 KB)

#### Quality
- **Excellent** - Comprehensive player stats
- **Coverage:** 2012-2024 seasons
- **Player IDs:** Includes player_id field
- **Rich Metrics:** Includes fantasy points, advanced stats, career totals

#### Schema Sample
Over 300 columns including:
- Player info: player_id, name, position, team, college
- Draft info: draft_year, draft_round, draft_pick
- Physical: height, weight, age, years_exp
- Snap counts and percentages
- Comprehensive offensive stats
- Season and career aggregates
- Fantasy scoring (PPR and standard)
- Delta columns (week-over-week changes)
- Team share percentages

#### Recommendation
**KEEP AND USE** - This is gold:
- Most comprehensive player stats found
- Weekly granularity for 13 seasons
- Includes player IDs for joining
- Perfect for time-series analysis
- Use as primary dataset for player performance analysis

---

### 2. NFL_Scraper Cache (256 MB)
Already described in repository section above. Same data as the repo.

#### Recommendation
**KEEP** - Current through 2025 Week 7, good for recent play-by-play data.

---

### 3. nfl-draft-data Cache (17 MB)
Already described in repository section above. Same data as the repo.

#### Recommendation
**KEEP** - Valuable for draft analysis through 2021.

---

### 4. NFL-Statistics-Scrape Cache (94 MB)
Already described in repository section above. Same data as the repo.

#### Recommendation
**KEEP FOR REFERENCE** - Historical game logs through ~2017.

---

## Overall Strategy & Recommendations

### Primary Data Strategy

#### 1. Use nflreadpy as Main Dependency
```bash
cd C:/Users/shays/code/gridiron-yampylytics
uv add nflreadpy
```

**Why:**
- Modern, actively maintained Python package
- Official nflverse project with daily updates
- Covers 95% of data needs
- Professional API with caching
- Uses fast Polars DataFrames

**Use for:**
- Play-by-play data (2000+)
- Current season data
- Player/team statistics
- Schedules, rosters, depth charts
- Draft picks, combine, injuries
- NextGen stats

#### 2. Keep Existing Cached Datasets
**High Value Cached Data:**
- **NFL Stats 2012-2024** (209 MB) - PRIMARY dataset for player analysis
- **NFL_Scraper** (256 MB) - Current 2025 data, play-by-play backup
- **nfl-draft-data** (17 MB) - Draft analysis 1967-2021

**Lower Priority:**
- **NFL-Statistics-Scrape** (94 MB) - Historical reference only

#### 3. Extract Reference Data from nfldata
Download just the `/data` directory CSVs:
- draft_picks.csv, draft_values.csv
- games.csv (with betting lines)
- teams.csv, logos.csv, teamcolors.csv
- trades.csv, standings.csv

**Don't clone the full repo** (7.2 GB git history not needed)

#### 4. Supplement with Targeted Downloads
For data not in cached sets or nflreadpy:
- **Spotrac scraper**: Test for current salary data
- **Recent drafts**: Use nflreadpy for 2022-2025 drafts

### Repository Actions

| Repository | Action | Reason |
|------------|--------|--------|
| nflreadpy | **Add as dependency** | Primary data source |
| nfldata | **Extract data files only** | Valuable reference data |
| NFL_Scraper | **Archive repo, keep cache** | Data already cached |
| nfl-draft-data | **Archive repo, keep cache** | Data already cached |
| historical-nfl-draft-data | **Archive** | Redundant |
| NFL-Combine-Data | **Archive** | Outdated, use nflreadpy |
| NFL-Statistics-Scrape | **Archive repo, keep cache** | Historical reference |
| Spotrac.com-NFL-Scrap | **Test and evaluate** | May be useful for salaries |
| nflscrapy | **Archive** | Redundant with nflreadpy |

### Data Gaps to Address

1. **Draft Data 2022-2025**: Use nflreadpy.load_draft_picks()
2. **Current Season Updates**: Set up nflreadpy to fetch latest weekly
3. **Contract/Salary Data**: Compare Spotrac scraper vs nflreadpy.load_contracts()
4. **Combine Data Recent**: Use nflreadpy.load_combine() for 2022-2025

### Storage Optimization

Current: ~7.9 GB in repos + 576 MB cached = 8.5 GB total

After cleanup:
- Remove 6 repository clones: -7.8 GB
- Keep nflreadpy repo: 1.5 MB
- Extract nfldata /data: +10 MB
- Keep cached data: 576 MB
- **New total: ~590 MB** (93% reduction)

### Implementation Plan

1. **Immediate:**
   - Add nflreadpy to project dependencies
   - Extract nfldata /data directory CSVs
   - Test nflreadpy data fetching

2. **Short Term:**
   - Write data loading utilities using nflreadpy
   - Validate cached data quality and coverage
   - Set up automated updates via nflreadpy

3. **Medium Term:**
   - Fill data gaps (2022-2025 drafts, current season)
   - Test Spotrac scraper for salary data
   - Create unified player ID mapping

4. **Cleanup:**
   - Archive 6 repositories (keep as zip backups if needed)
   - Document data sources and update frequency
   - Create data dictionary for cached datasets

---

## Data Quality Assessment

### Player ID Strategy

**Multiple ID systems found:**
1. **nflfastR/nflverse player_id** - Most common in cached stats
2. **Pro Football Reference pfr_id** - In nfldata draft/roster files
3. **ESPN player_id / guid** - In draft prospect data
4. **NFL.com URL identifier** - In NFL-Statistics-Scrape

**Recommendation:** Use nflverse player_id as primary, maintain mapping table to others

### Data Completeness

**Well Covered:**
- Player statistics: 2012-2025 (weekly and season)
- Play-by-play: 2017-2025 (NFL_Scraper), 2000+ via nflreadpy
- Draft picks: 1967-2021 (nfl-draft-data), 2000+ (nfldata)
- Schedules/Games: 2006+ (nfldata)

**Gaps:**
- Draft picks: 2022-2025 (need to fetch)
- Combine: Recent years (use nflreadpy)
- Injuries: (available via nflreadpy)
- Contract/salary: Uncertain quality

### Data Freshness

**Most Current Sources:**
1. **nflreadpy**: Daily automated updates
2. **NFL_Scraper cached**: Through 2025 Week 7
3. **nfldata**: Daily updates (if we fetch directly)
4. **NFL Stats 2012-2024**: Through 2024 season

**Action:** Set up weekly/monthly nflreadpy data refreshes

---

## Conclusion

We have excellent data coverage across multiple sources, with the primary finding being that **nflreadpy should be our main dependency** moving forward. The cached datasets, particularly the NFL Stats 2012-2024, provide comprehensive historical player statistics that complement nflreadpy's capabilities.

**Key Strengths:**
- Comprehensive player stats (2012-2025)
- Current play-by-play data (through 2025 Week 7)
- Historical draft data (1967-2021)
- Professional tooling via nflreadpy

**Next Steps:**
1. Integrate nflreadpy as dependency
2. Extract nfldata reference files
3. Fill 2022-2025 draft gap
4. Archive redundant repositories
5. Document final data architecture

**Total Usable Data:** ~590 MB after cleanup (down from 8.5 GB)
