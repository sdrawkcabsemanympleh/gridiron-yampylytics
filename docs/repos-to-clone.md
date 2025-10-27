# GitHub Repositories to Clone

These repos provide pre-built data and scrapers we can adapt for gridiron-yampylytics.

## Pre-built Data (CSV files ready to use)

### 1. Lee Sharpe's nfldata
**URL:** `https://github.com/leesharpe/nfldata`
**Contains:** Draft picks CSV (2000+), combine data, PFR data
**Priority:** HIGH - Has clean CSV files we can use immediately
**Clone to:** `external-repos/nfldata/`

### 2. Historical NFL Draft Data
**URL:** `https://github.com/Leagify/historical-nfl-draft-data`
**Contains:** Historical draft class data from PFR
**Priority:** MEDIUM - Good for backfill if nfldata doesn't have early years
**Clone to:** `external-repos/historical-nfl-draft-data/`

### 3. NFL Draft Data with College Stats
**URL:** `https://github.com/JackLich10/nfl-draft-data`
**Contains:** Draft prospects back to 1967 with college statistics
**Priority:** LOW - Nice to have if we need college context later
**Clone to:** `external-repos/nfl-draft-data/`

---

## Python Scrapers (to adapt/reuse)

### 4. NFL Combine Data Scraper
**URL:** `https://github.com/Johnny-Codes/NFL-Combine-Data`
**Contains:** Python scraper for nflcombineresults.com and PFR
**Priority:** HIGH - Can adapt for our combine data handler
**Clone to:** `external-repos/NFL-Combine-Data/`

### 5. Spotrac Salary Scraper
**URL:** `https://github.com/mipsbe/Spotrac.com-NFL-Scrap`
**Contains:** Python scraper for Spotrac salary/contract data
**Priority:** MEDIUM - Will need for Phase 1 contract handler
**Clone to:** `external-repos/Spotrac.com-NFL-Scrap/`

### 6. Generic PFR Scraper
**URL:** `https://github.com/ewelchman/scrape_pfr`
**Contains:** Generic Pro Football Reference scraper
**Priority:** MEDIUM - Useful reference for building our scrapers
**Clone to:** `external-repos/scrape_pfr/`

### 7. Comprehensive PFR Library
**URL:** `https://github.com/tefirman/sportsref-nfl`
**Contains:** Full library for PFR (schedules, stats, draft, ELO)
**Priority:** LOW - Comprehensive but may be overkill, good reference
**Clone to:** `external-repos/sportsref-nfl/`

---

## Commands to Clone All

```bash
# Navigate to gridiron-yampylytics root
cd gridiron-yampylytics

# Create external-repos directory
mkdir external-repos
cd external-repos

# Clone pre-built data repos
git clone https://github.com/leesharpe/nfldata
git clone https://github.com/Leagify/historical-nfl-draft-data
git clone https://github.com/JackLich10/nfl-draft-data

# Clone scraper repos
git clone https://github.com/Johnny-Codes/NFL-Combine-Data
git clone https://github.com/mipsbe/Spotrac.com-NFL-Scrap
git clone https://github.com/ewelchman/scrape_pfr
git clone https://github.com/tefirman/sportsref-nfl

# Return to project root
cd ..
```

---

## After Cloning - Inventory Tasks

1. **Check Lee Sharpe's data directory** - What CSVs are available? Years covered?
2. **Review combine scraper code** - What's the scraping pattern? Rate limiting?
3. **Review Spotrac scraper** - How does it handle pagination? Auth needed?
4. **Document findings** - Create inventory doc with what we found

---

## Note on .gitignore

Add `external-repos/` to `.gitignore` since we don't want to version control other people's repos:

```gitignore
# External reference repositories
external-repos/
```
