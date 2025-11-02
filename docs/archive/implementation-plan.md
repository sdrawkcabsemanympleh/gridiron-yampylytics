# Gridiron-Yampylytics Implementation Plan

## Project Vision

Build a reusable NFL GM analytics platform that:
- Acquires data from multiple sources (APIs, scraping, existing datasets)
- Stores raw and processed data with versioning
- Transforms and loads into queryable format (RDB + scripts)
- Calculates GM performance metrics
- Generates reports and visualizations

This is NOT a one-off analysis - it's a data platform designed for reuse, updates, and sharing.

---

## Architecture Overview

```
gridiron-yampylytics/
├── data/
│   ├── raw/                    # Untouched source data with timestamps
│   │   ├── nflverse/
│   │   ├── combine/
│   │   ├── contracts/
│   │   └── gm_history/
│   ├── processed/              # Cleaned, normalized data ready for loading
│   └── manifest.json           # What we have, when scraped, versions
├── src/gridiron_yampylytics/
│   ├── acquisition/            # Data source handlers
│   │   ├── base.py            # BaseDataHandler class
│   │   ├── mixins.py          # ScraperMixin, etc.
│   │   ├── nflverse.py        # nfl_data_py wrapper
│   │   ├── combine.py         # Combine data handler
│   │   ├── contracts.py       # Spotrac scraper
│   │   └── gm_history.py      # GM/coach history handler
│   ├── transform/              # Data cleaning and normalization
│   ├── storage/                # Database schema, loaders
│   ├── analysis/               # Metric calculations
│   └── reporting/              # Visualization and reports
├── scripts/                    # User-facing utilities
├── docs/                       # Documentation
└── config/                     # Configuration files
```

---

## Core Design Patterns

### Data Handler Class Hierarchy

**BaseDataHandler** - Abstract base class with standard interface:
```python
class BaseDataHandler:
    def backfill(self, years: list[int]) -> None:
        """Download historical data for specified years."""

    def update(self) -> None:
        """Download latest data since last run."""

    def validate(self) -> bool:
        """Run sanity checks on downloaded data."""
```

**ScraperMixin** - For sources that require web scraping:
```python
class ScraperMixin:
    def _scrape_with_retry(self, url: str, max_retries: int = 3) -> Response:
        """Scrape with exponential backoff and rate limiting."""

    def _respect_rate_limit(self) -> None:
        """Enforce configured rate limits."""
```

**Example Implementation:**
```python
class CombineDataHandler(BaseDataHandler, ScraperMixin):
    def backfill(self, years: list[int]) -> None:
        # Use ScraperMixin for PFR scraping

    def update(self) -> None:
        # Get most recent combine data

    def validate(self) -> bool:
        # Check expected columns, row counts, etc.
```

---

## Phase 0: Setup & Discovery

**Goal:** Understand what's available, set up structure, test tools

**Tasks:**
1. Clone GitHub repos for inspection
2. Test nfl_data_py to see what it provides
3. Inventory existing CSV datasets
4. Document player ID schemes (gsis_id, pfr_player_id, etc.)
5. Create initial project structure
6. Set up configuration management

**Deliverables:**
- List of repos cloned locally
- Test notebook/script showing nfl_data_py usage
- Initial data/raw/ directory structure
- Player ID linking documentation
- config/sources.yaml configuration file

---

## Phase 1: Acquisition Tooling

**Goal:** Build reusable data acquisition modules

**Data Sources & Approach:**

### 1. NFLverse Data (nfl_data_py)
**Handler:** `NflverseDataHandler`
**Data:** Play-by-play, rosters, draft picks, schedules, depth charts
**Approach:** Wrapper around existing library
**Difficulty:** Easy
**Priority:** HIGH - Start here

### 2. Combine Data
**Handler:** `CombineDataHandler`
**Data:** 40-time, bench, vertical, broad jump, etc.
**Approach:**
- Option A: Download from existing repo (Lee Sharpe, Johnny-Codes)
- Option B: Scrape PFR if we need fresher data
**Difficulty:** Easy (download) / Medium (scrape)
**Priority:** HIGH

### 3. Contract/Salary Data
**Handler:** `ContractDataHandler` (uses ScraperMixin)
**Data:** Cap hits, dead money, contract years
**Source:** Spotrac
**Approach:** Adapt existing scraper (mipsbe/Spotrac.com-NFL-Scrap)
**Difficulty:** Medium
**Priority:** Medium - can analyze a lot without this

### 4. GM/Coach History
**Handler:** `GmHistoryHandler`
**Data:** GM name, coach name, team, years
**Approach:**
- Phase 1: Manual CSV for key GMs
- Phase 2: Scrape PFR team pages if needed
**Difficulty:** Easy (manual) / Medium (scrape)
**Priority:** HIGH - need this to attribute decisions

### 5. Draft Value Charts
**Handler:** `DraftValueHandler`
**Data:** Jimmy Johnson, Rich Hill trade value charts
**Approach:** Simple CSV or existing dataset
**Difficulty:** Trivial
**Priority:** Low - nice to have

**Deliverables:**
- BaseDataHandler abstract class
- ScraperMixin for web scraping with retry/rate limiting
- One handler per data source (5 total)
- All handlers tested with small backfill
- Raw data stored in data/raw/ with timestamps

---

## Phase 2: Storage & Manifest

**Goal:** Track what data we have, when we got it, version it properly

**Tasks:**
1. Design manifest.json schema
2. Implement manifest read/write utilities
3. Tag all raw data files with scraped_at timestamps
4. Create data inventory script (what years, what sources)
5. Document data freshness expectations

**Manifest Schema:**
```json
{
  "nflverse_pbp": {
    "years": [1999, 2000, ..., 2024],
    "last_updated": "2024-10-26T15:30:00",
    "record_count": 1250000,
    "file_path": "data/raw/nflverse/pbp_1999_2024.csv"
  },
  "combine": {
    "years": [2000, 2001, ..., 2024],
    "last_updated": "2024-10-26T15:45:00",
    "record_count": 15000,
    "file_path": "data/raw/combine/combine_2000_2024.csv"
  }
}
```

**Deliverables:**
- manifest.json file
- Manifest utility class
- Data inventory script
- Documentation on data freshness

---

## Phase 3: Transformation Layer

**Goal:** Clean, normalize, and prepare data for analysis

**Key Transformations:**
1. **Player ID Normalization** - Link across datasets using gsis_id, pfr_player_id
2. **Team Code Standardization** - Ensure consistent 3-letter codes (ARI, ATL, etc.)
3. **Position Normalization** - Handle variations (WR vs SLOT, etc.)
4. **Missing Data Handling** - Document approach for nulls, unknowns
5. **Derived Fields** - Calculate snap counts, snap percentages, etc.

**Tasks:**
1. Analyze raw data quality (missing values, inconsistencies)
2. Build transformation modules
3. Create processed datasets
4. Document all transformation decisions
5. Build validation tests

**Deliverables:**
- Transformation scripts in src/gridiron_yampylytics/transform/
- Processed data in data/processed/
- Transformation documentation
- Player ID linking strategy document

---

## Phase 4: Database Design

**Goal:** Structured queryable storage

**Approach:** SQLite for simplicity and portability

**Schema (preliminary):**
- **players** - Master player list with IDs
- **teams** - Team info (abbreviation, full name, city)
- **games** - Game schedule, scores
- **draft_picks** - Pick number, player, team, year
- **snap_counts** - Player snaps by game/season
- **combine_results** - Athletic testing results
- **contracts** - Cap hits, dead money by player/year
- **gm_tenure** - GM/coach assignments by team/year

**Tasks:**
1. Design schema
2. Create SQLite database
3. Build loaders from processed CSVs
4. Index for common queries
5. Test query performance

**Deliverables:**
- Schema documentation
- SQLite database file
- Load scripts
- Query examples

---

## Phase 5: Analysis Framework

**Goal:** Calculate GM performance metrics

**Metrics to Implement (from roadmap):**

**Basic (just nflverse data):**
1. Snap Count Totals - Career snaps by draft pick
2. Draft Hit Rate - % picks with >1000 career snaps
3. Positional Drafting Patterns - Over/under draft positions by GM
4. Roster Churn Rate - Players added/dropped per season
5. Depth Chart Velocity - How fast rookies become starters

**With Combine Data:**
6. Athletic Profile by Position - Do GMs draft faster/stronger?
7. Combine Score vs Production - Which metrics predict success?

**With GM History:**
8. GM Rankings - Sort all metrics by GM tenure

**With Contracts:**
9. Dead Money Disaster Index - % of cap wasted
10. Rookie Contract Efficiency - Snaps per dollar on rookie deals

**Tasks:**
1. Build metric calculation modules
2. Create query helpers
3. Implement each metric
4. Validate results with known good/bad GMs

**Deliverables:**
- Metric calculation functions
- Query helper utilities
- Metric results datasets
- Validation documentation

---

## Phase 6: Reporting

**Goal:** Visualize and share findings

**Formats:**
- Retro-style reports (mentioned in original roadmap)
- CSV exports for further analysis
- Dashboards (Streamlit/Plotly?)
- Static visualizations (matplotlib/seaborn)

**Tasks:**
1. Build visualization utilities
2. Create report templates
3. Generate initial GM rankings
4. Find funny/absurd metrics

**Deliverables:**
- Reporting scripts
- Example reports
- Visualization gallery

---

## GitHub Repositories to Clone

**Pre-built Data:**
1. `https://github.com/leesharpe/nfldata` - Draft picks, combine, PFR data
2. `https://github.com/Leagify/historical-nfl-draft-data` - Historical draft classes
3. `https://github.com/JackLich10/nfl-draft-data` - Draft prospects with college stats

**Python Scrapers:**
4. `https://github.com/Johnny-Codes/NFL-Combine-Data` - Combine scraper
5. `https://github.com/mipsbe/Spotrac.com-NFL-Scrap` - Spotrac salary scraper
6. `https://github.com/ewelchman/scrape_pfr` - Generic PFR scraper
7. `https://github.com/tefirman/sportsref-nfl` - Comprehensive PFR library

---

## Configuration Management

**config/sources.yaml:**
```yaml
nflverse:
  years: [1999, 2024]
  datasets:
    - play_by_play
    - weekly_rosters
    - draft_picks
    - depth_charts
    - schedules

scraping:
  rate_limits:
    pfr: 1.0  # seconds between requests
    spotrac: 2.0
  retry:
    max_attempts: 3
    backoff_factor: 2.0

teams:
  codes: [ARI, ATL, BAL, BUF, CAR, CHI, CIN, CLE, DAL, DEN, DET, GB, HOU, IND, JAX, KC, LAC, LAR, LV, MIA, MIN, NE, NO, NYG, NYJ, PHI, PIT, SEA, SF, TB, TEN, WAS]
```

---

## Key Design Principles

1. **Idempotency** - Safe to re-run acquisition scripts
2. **Versioning** - Timestamp all data, track provenance
3. **Validation** - Sanity checks at each stage
4. **Documentation** - Explain WHY not just WHAT
5. **Reusability** - Designed for updates and sharing
6. **Respectful Scraping** - Rate limits, retry logic, caching

---

## Player ID Linking Strategy

**Key Fields:**
- `gsis_id` - NFL's official Game Statistics & Information System ID
- `pfr_player_id` - Pro Football Reference ID
- `espn_id` - ESPN player ID
- `fantasy_data_id` - Fantasy data services ID

**Approach:**
- nfl_data_py provides ID mappings across systems
- Use gsis_id as primary key where available
- Fall back to pfr_player_id for historical data
- Document any manual matches needed

**To Document:**
- Which datasets use which IDs
- How to join across sources
- Edge cases (name changes, corrections)

---

## Next Steps

**Immediate (Phase 0):**
1. Clone repos from GitHub
2. Test nfl_data_py
3. Create project structure
4. Draft config/sources.yaml

**Week 1 (Phase 1):**
1. Build BaseDataHandler and ScraperMixin
2. Implement NflverseDataHandler
3. Implement CombineDataHandler
4. Test small backfill

**Questions to Resolve:**
- SQLite vs Postgres vs just CSVs?
- How much historical data to start with? (all years or last 5?)
- Priority on contract data? (complex to scrape)
- Visualization preferences? (retro reports, dashboards, both?)
